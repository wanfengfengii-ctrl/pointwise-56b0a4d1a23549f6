import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from demo import running
from lamp.service import make_lamp_server
from rehearsal.application import ConsoleHandler, make_console_server


class DemoConsoleHandler(ConsoleHandler):
    def _get(self):
        if self.path == '/healthz':
            return {'status': 'ready'}
        return super()._get()


def main():
    parser = argparse.ArgumentParser(description='Start the two rehearsal services')
    parser.add_argument('--host', choices=('127.0.0.1',), default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with TemporaryDirectory() as folder:
        store = Path(folder)
        with running(make_lamp_server(store / 'lamp.sqlite')) as lamp:
            with make_console_server(store / 'console.sqlite', lamp, args.port) as console:
                console.RequestHandlerClass = DemoConsoleHandler
                print(f'READY http://{args.host}:{console.server_port}', flush=True)
                print(f'LAMP {lamp}', flush=True)
                try:
                    console.serve_forever()
                except KeyboardInterrupt:
                    return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
