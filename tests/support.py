from http.server import ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Lock, Thread
import unittest
from urllib.parse import urlsplit

from service_support import JsonHandler, Problem, TransportError, request_json


class ServiceProcess:
    def __init__(self, role, store):
        self.role = role
        self.store = store
        self.child = None
        self.url = None

    def start(self, *args):
        command = [sys.executable, '-B', '-m', 'rehearsal.application', self.role,
                   '--port', '0', '--db', str(self.store), *args]
        self.child = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding='utf-8', errors='replace')
        lines = Queue()

        def drain(stream):
            for line in stream:
                lines.put(line.rstrip())
            lines.put(None)

        self.reader = Thread(target=drain, args=(self.child.stdout,), daemon=True)
        self.reader.start()
        startup = []
        try:
            for _ in range(40):
                line = lines.get(timeout=10)
                if line is None:
                    break
                if line.startswith('READY '):
                    self.url = line.removeprefix('READY ')
                    return
                startup.append(line)
        except Empty:
            startup.append('timed out waiting for READY')
        self.stop()
        raise RuntimeError(f'{self.role} failed to start: {startup}')

    def stop(self):
        if self.child is None:
            return
        if self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait(timeout=5)
        self.reader.join(timeout=5)
        self.child.stdout.close()
        self.child = None
        self.url = None


class DropConnection(Exception):
    pass


class Gate:
    def __init__(self, route, *, matches=None, hold=False, drop_before=False, drop_reply=False):
        self.route = route
        self.matches = matches or {}
        self.drop_before = drop_before
        self.drop_reply = drop_reply
        self.entered = Event()
        self.release = Event()
        self.committed_reply = Event()
        if not hold:
            self.release.set()


class RelayHandler(JsonHandler):
    def do_GET(self):
        self._relay()

    def do_POST(self):
        self._relay()

    def _relay(self):
        try:
            self.respond(self._forward)
        except DropConnection:
            self.close_connection = True

    def _forward(self):
        route = urlsplit(self.path).path
        body = self.read_body() if self.command == 'POST' else None
        query = self.read_query() if body is None else None
        gate = self.server.take_gate(route, query if body is None else body)
        if gate is not None:
            gate.entered.set()
            if not gate.release.wait(timeout=15):
                raise Problem(503, 'relay_gate_timeout')
            if gate.drop_before:
                raise DropConnection
        try:
            result = request_json(self.server.target, route, body=body, query=query)
        except TransportError as exc:
            raise Problem(503, 'relay_unavailable') from exc
        if gate is not None:
            gate.committed_reply.set()
            if gate.drop_reply:
                raise DropConnection
        return result


class Relay(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(('127.0.0.1', 0), RelayHandler)
        self.target = None
        self.gate = None
        self.lock = Lock()
        self.thread = Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server_port}'

    def arm(self, gate):
        with self.lock:
            if self.gate is not None:
                raise RuntimeError('an unclaimed relay gate is already armed')
            self.gate = gate
        return gate

    def take_gate(self, route, arguments):
        with self.lock:
            gate = self.gate
            if gate is None or gate.route != route:
                return None
            if any(arguments.get(key) != value for key, value in gate.matches.items()):
                return None
            self.gate = None
            return gate

    def stop(self):
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=5)


class RehearsalCase(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.relay = Relay()
        self.addCleanup(self.relay.stop)
        self.lamp = ServiceProcess('lamp', root / 'lamp.sqlite')
        self.addCleanup(self.lamp.stop)
        self.console = ServiceProcess('console', root / 'console.sqlite')
        self.addCleanup(self.console.stop)
        self.start_services()

    def start_services(self):
        self.lamp.start()
        self.relay.target = self.lamp.url
        self.start_console()

    def start_console(self):
        self.console.start('--lamp-url', self.relay.url)

    def restart(self):
        self.console.stop()
        self.lamp.stop()
        self.start_services()

    def post(self, route, *, onsite=False, **body):
        base = self.lamp.url if onsite else self.console.url
        return request_json(base, route, body=body)

    def get(self, route, *, onsite=False, **query):
        base = self.lamp.url if onsite else self.console.url
        return request_json(base, route, query=query)

    def reject(self, status, code, call, *args, **kwargs):
        with self.assertRaises(Problem) as raised:
            call(*args, **kwargs)
        self.assertEqual((raised.exception.status, raised.exception.code), (status, code))

    def make_edition(self, levels, *, scene='opening'):
        self.post('/draft', scene=scene, levels=levels)
        return self.post('/proof', scene=scene)

    def prepare(self, initial=80, *, session='R1'):
        self.post('/fixture', fixture='F1', label='前区灯')
        edition = self.make_edition({'F1': initial})
        return self.post('/open', session=session, edition=edition['edition'])

    def adjust(self, action, delta, *, session='R1', fixture='F1', onsite=False):
        return self.post('/local' if onsite else '/adjust', onsite=onsite,
                         session=session, fixture=fixture, action=action, delta=delta)

    def withdraw(self, action='W', target='A', *, session='R1', fixture='F1'):
        return self.post('/withdraw', session=session, fixture=fixture, action=action, target=target)

    def current(self, session='R1', fixture='F1'):
        return self.get('/current', onsite=True, session=session, fixture=fixture)

    def receipt(self, action, session='R1'):
        return self.get('/receipt', session=session, action=action)

    def first(self, action, *, session='R1', source='desk'):
        return self.get('/first', onsite=True, session=session, source=source, action=action)

    def target_history(self, delta, *, session='R1', source='local'):
        self.prepare(session=session)
        receipts = [self.adjust('A', 30, session=session),
                    self.adjust('L', delta, session=session, onsite=source == 'local'),
                    self.adjust('C', -10, session=session)]
        self.assertEqual([row['level'] for row in receipts], [100, 100, 90])
        self.assertEqual([row['seq'] for row in receipts], [2, 3, 4])
        return receipts
