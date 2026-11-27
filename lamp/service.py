from dataclasses import asdict
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

from lamp.commands import (
    execute_desk_command,
    initialize_execution_store,
    initialize_session,
    preview_withdrawal,
    read_execution_receipt,
    read_sealed_cut,
    seal_session,
)
from lamp.emissions import read_current
from lamp.local import submit_local_adjustment
from service_support import JsonHandler, Problem, database, level_map, request_json, text_field


class LampHandler(JsonHandler):
    def do_GET(self):
        self.respond(self._get)

    def do_POST(self):
        self.respond(self._post)

    def _get(self):
        route = urlsplit(self.path).path
        query = self.read_query()
        path = self.server.store
        if route == '/current':
            session = text_field(query, 'session')
            fixture = text_field(query, 'fixture')
            with database(path) as db:
                found = read_current(db, session, fixture)
            if found is None:
                raise Problem(404, 'unknown_binding')
            return asdict(found)
        if route == '/preview-withdrawal':
            return preview_withdrawal(path, text_field(query, 'session'),
                                      text_field(query, 'fixture'), text_field(query, 'target'))
        if route == '/first':
            session = text_field(query, 'session')
            source = text_field(query, 'source')
            action = text_field(query, 'action')
            if source not in ('desk', 'local', 'initial'):
                raise Problem(400, 'invalid_source')
            with database(path) as db:
                return read_execution_receipt(db, session, source, action)
        if route == '/cut':
            session = text_field(query, 'session')
            try:
                cutoff = int(text_field(query, 'cutoff'))
            except ValueError as exc:
                raise Problem(400, 'invalid_cutoff') from exc
            return read_sealed_cut(path, session, cutoff)
        raise Problem(404, 'unknown_route')

    def _post(self):
        route = urlsplit(self.path).path
        body = self.read_body()
        path = self.server.store
        if route == '/local':
            return submit_local_adjustment(path, body)
        if route == '/command':
            return execute_desk_command(path, body)
        if route == '/initialize':
            return initialize_session(path, text_field(body, 'session'),
                                      text_field(body, 'edition'), level_map(body))
        if route == '/seal':
            return seal_session(path, text_field(body, 'session'))
        raise Problem(404, 'unknown_route')


def make_lamp_server(path, port=0):
    initialize_execution_store(path)
    server = ThreadingHTTPServer(('127.0.0.1', port), LampHandler)
    server.store = path
    return server


class LampClient:
    def __init__(self, base):
        parts = urlsplit(base.rstrip('/'))
        if (parts.scheme != 'http' or parts.hostname != '127.0.0.1' or not parts.port
                or parts.username is not None or parts.path or parts.query or parts.fragment):
            raise ValueError('lamp URL must be an HTTP loopback address with a port')
        self.base = f'http://127.0.0.1:{parts.port}'

    def initialize_session(self, session, edition, levels):
        return request_json(self.base, '/initialize', body={
            'session': session, 'edition': edition, 'levels': levels,
        })

    def read_current(self, session, fixture):
        return request_json(self.base, '/current', query={'session': session, 'fixture': fixture})

    def preview_withdrawal(self, session, fixture, target):
        return request_json(self.base, '/preview-withdrawal', query={
            'session': session, 'fixture': fixture, 'target': target,
        })

    def submit_command(self, command):
        return request_json(self.base, '/command', body=command)

    def read_first_emission(self, session, source, action):
        return request_json(self.base, '/first', query={
            'session': session, 'source': source, 'action': action,
        })

    def seal_session(self, session):
        return request_json(self.base, '/seal', body={'session': session})

    def read_cut(self, session, cutoff):
        return request_json(self.base, '/cut', query={'session': session, 'cutoff': cutoff})
