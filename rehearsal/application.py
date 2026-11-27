import argparse
from dataclasses import asdict
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

from desk.adjustments import submit_adjustment
from desk.receipts import read_receipt
from desk.request_book import ensure_request_schema
from desk.withdrawals import submit_withdrawal
from lamp.service import LampClient, make_lamp_server
from rehearsal.bindings import ensure_binding_schema
from rehearsal.closing import close_session
from rehearsal.opening import open_session
from rehearsal.sessions import ensure_session_schema
from review.archive import ensure_archive_schema, read_report
from scene.drafts import ensure_draft_schema, read_draft, save_draft
from scene.editions import ensure_edition_schema, read_edition
from scene.fixtures import ensure_fixture_schema, find_fixture, register_fixture
from scene.proofs import proof_scene
from service_support import JsonHandler, Problem, database, level_map, text_field


def initialize_console_store(path):
    with database(path, write=True) as db:
        ensure_fixture_schema(db)
        ensure_draft_schema(db)
        ensure_edition_schema(db)
        ensure_session_schema(db)
        ensure_binding_schema(db)
        ensure_request_schema(db)
        ensure_archive_schema(db)


class ConsoleHandler(JsonHandler):
    def do_GET(self):
        self.respond(self._get)

    def do_POST(self):
        self.respond(self._post)

    def _get(self):
        route = urlsplit(self.path).path
        query = self.read_query()
        path = self.server.store
        if route == '/receipt':
            return read_receipt(path, self.server.lamp, text_field(query, 'session'),
                                text_field(query, 'action'))
        with database(path) as db:
            if route == '/report':
                report = read_report(db, text_field(query, 'report'))
                if report is None:
                    raise Problem(404, 'unknown_report')
                return report
            if route == '/fixture':
                fixture = find_fixture(db, text_field(query, 'fixture'))
                if fixture is None:
                    raise Problem(404, 'unknown_fixture')
                return fixture
            if route == '/draft':
                draft = read_draft(db, text_field(query, 'scene'))
                if draft is None:
                    raise Problem(404, 'unknown_draft')
                return asdict(draft)
            if route == '/edition':
                edition = read_edition(db, text_field(query, 'edition'))
                if edition is None:
                    raise Problem(404, 'unknown_edition')
                return asdict(edition)
        raise Problem(404, 'unknown_route')

    def _post(self):
        route = urlsplit(self.path).path
        body = self.read_body()
        path = self.server.store
        lamp = self.server.lamp
        if route == '/open':
            return open_session(path, lamp, text_field(body, 'session'), text_field(body, 'edition'))
        if route == '/adjust':
            return submit_adjustment(path, lamp, body)
        if route == '/withdraw':
            return submit_withdrawal(path, lamp, body)
        if route == '/close':
            return close_session(path, lamp, text_field(body, 'session'))
        if route in ('/fixture', '/draft', '/proof'):
            with database(path, write=True) as db:
                if route == '/fixture':
                    return register_fixture(db, text_field(body, 'fixture'), text_field(body, 'label'))
                scene = text_field(body, 'scene')
                if route == '/draft':
                    return asdict(save_draft(db, scene, level_map(body)))
                return asdict(proof_scene(db, scene))
        raise Problem(404, 'unknown_route')


def make_console_server(path, lamp_url, port=0):
    lamp = LampClient(lamp_url)
    initialize_console_store(path)
    server = ThreadingHTTPServer(('127.0.0.1', port), ConsoleHandler)
    server.store = path
    server.lamp = lamp
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description='Rehearsal light HTTP services')
    commands = parser.add_subparsers(dest='service', required=True)
    lamp = commands.add_parser('lamp')
    console = commands.add_parser('console')
    for subparser, port in ((lamp, 8766), (console, 8765)):
        subparser.add_argument('--db', required=True)
        subparser.add_argument('--port', type=int, default=port)
    console.add_argument('--lamp-url', default='http://127.0.0.1:8766')
    args = parser.parse_args(argv)
    if args.service == 'lamp':
        server = make_lamp_server(args.db, args.port)
    else:
        server = make_console_server(args.db, args.lamp_url, args.port)
    with server:
        print(f'READY http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
