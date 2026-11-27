import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread

from lamp.service import make_lamp_server
from rehearsal.application import make_console_server
from service_support import request_json


@contextmanager
def running(server):
    with server:
        worker = Thread(target=server.serve_forever)
        worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            worker.join()


def run(console, lamp, incident):
    request_json(console, '/fixture', body={'fixture': 'F1', 'label': '前区灯'})
    for initial in (80, 30):
        request_json(console, '/draft', body={'scene': 'opening', 'levels': {'F1': initial}})
        edition = request_json(console, '/proof', body={'scene': 'opening'})
        if initial == 80:
            selected = edition['edition']
    opened = request_json(console, '/open', body={'session': 'R1', 'edition': selected})
    ref = {'session': 'R1', 'fixture': 'F1'}
    before = [opened['initial'][0]['level']]
    for base, route, action, delta in (
        (console, '/adjust', 'A', 30), (lamp, '/local', 'L', 10), (console, '/adjust', 'C', -10),
    ):
        receipt = request_json(base, route, body={**ref, 'action': action, 'delta': delta})
        before.append(receipt['level'])
    if before != [80, 100, 100, 90]:
        raise RuntimeError(f'unexpected setup levels: {before}')
    withdrawn = request_json(console, '/withdraw', body={**ref, 'action': 'W', 'target': 'A'})
    current = request_json(lamp, '/current', query=ref)
    if (withdrawn.get('status') != 'applied' or withdrawn.get('action') != 'W'
            or withdrawn.get('seq') != 5 or current.get('seq') != 5
            or current.get('action') != 'W' or type(withdrawn.get('level')) is not int
            or type(current.get('level')) is not int):
        raise RuntimeError(f'withdrawal did not confirm an emission: {withdrawn}, {current}')
    actual = [withdrawn['level'], current['level']]
    if actual != [80, 80]:
        print(f'WRONG_UNDO_LEVEL expected=[80, 80] actual={actual}', file=sys.stderr)
        return 1
    if incident:
        print(json.dumps({'before': before, 'withdrawal': withdrawn, 'current': current}))
        return 0
    original = request_json(console, '/receipt', query={'session': 'R1', 'action': 'W'})
    closed = request_json(console, '/close', body={'session': 'R1'})
    report = request_json(console, '/report', query={'report': closed['report']})
    levels = [row['level'] for row in report['timeline']]
    identities = [(row['source'], row['action']) for row in report['sources']]
    if (original != withdrawn or levels != [80, 100, 100, 90, 80]
            or identities != [('initial', 'F1'), ('desk', 'A'), ('local', 'L'),
                              ('desk', 'C'), ('desk', 'W')]):
        raise RuntimeError('handoff report differs from the actual rehearsal')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--incident', action='store_true')
    args = parser.parse_args()
    with TemporaryDirectory() as folder:
        root = Path(folder)
        with running(make_lamp_server(root / 'lamp.sqlite')) as lamp:
            with running(make_console_server(root / 'console.sqlite', lamp)) as console:
                return run(console, lamp, args.incident)


if __name__ == '__main__':
    raise SystemExit(main())
