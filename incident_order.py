from concurrent.futures import ThreadPoolExecutor
import sys
import unittest

from tests.support import Gate, RehearsalCase


class WithdrawalOrder(RehearsalCase):
    def test_withdrawal_crosses_live_adjustment(self):
        self.prepare(60)
        self.adjust('A', 20)
        self.adjust('B', -10)
        gate = self.relay.arm(Gate('/command', matches={'action': 'W'}, hold=True))
        with ThreadPoolExecutor(max_workers=1) as workers:
            future = workers.submit(self.withdraw)
            try:
                if not gate.entered.wait(8):
                    raise RuntimeError('withdrawal did not reach the relay')
                local = self.adjust('M', 5, onsite=True)
                self.assertEqual((local['level'], local['seq']), (75, 4))
            finally:
                gate.release.set()
            result = future.result(timeout=10)
        current = self.current()
        self.assertEqual((result['status'], result['action'], result['seq']), ('applied', 'W', 5))
        self.assertEqual((current['action'], current['seq']), ('W', 5))
        actual = (result['level'], current['level'])
        if actual != (55, 55):
            print(f'WRONG_UNDO_ORDER expected=(55, 55) actual={actual}', file=sys.stderr)
            self.fail('a local adjustment accepted before withdrawal must survive it')
        print(f'withdrawal={result["level"]} current={current["level"]} seq={current["seq"]}')


if __name__ == '__main__':
    unittest.main()
