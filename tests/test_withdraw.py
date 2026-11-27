from concurrent.futures import ThreadPoolExecutor
import json

from tests.support import Gate, RehearsalCase


class TestWithdraw(RehearsalCase):
    def test_saturated_local_action(self):
        actual = []
        downstream = []
        for session, delta in (('R1', 10), ('R2', 0)):
            old = self.target_history(delta, session=session)
            result = self.withdraw(session=session)
            current = self.current(session)
            actual.append([row['level'] for row in old] + [result['level']])
            downstream.append([current['level'], self.receipt('W', session)['level']])
            self.assertEqual(result['seq'], 5)
            self.assertEqual(self.receipt('A', session), old[0])
            self.assertEqual(self.first('L', session=session, source='local'), old[1])
        expected = [[100, 100, 90, 80], [100, 100, 90, 70]]
        downstream_expected = [[80, 80], [70, 70]]
        self.assertEqual(actual, expected)
        self.assertEqual(downstream, downstream_expected)
        evidence = {
            'case_id': 'v5',
            'input': {'initial': 80, 'desk': [30, -10], 'local': [10, 0], 'withdraw': 'A'},
            'expected': expected,
            'actual': actual,
            'downstream_expected': downstream_expected,
            'downstream_actual': downstream,
            'code_paths': ['desk/dispatch.py', 'lamp/commands.py', 'lamp/action_history.py',
                           'lamp/levels.py', 'desk/receipts.py'],
            'oracle': '去掉 +30 后，手算 80 + 10 - 10 = 80，80 + 0 - 10 = 70。两轮首执与现值都应相符。',
        }
        print('POINTWISE_SCENARIO ' + json.dumps(evidence, ensure_ascii=False))

    def test_desk_intent(self):
        for session, delta, expected in (('R1', 10, 80), ('R2', 0, 70)):
            with self.subTest(delta=delta):
                old = self.target_history(delta, session=session, source='desk')
                withdrawn = self.withdraw(session=session)
                self.assertEqual((withdrawn['level'], self.current(session)['level']), (expected, expected))
                self.assertEqual(self.first('L', session=session)['delta'], delta)
                self.assertEqual(self.receipt('L', session), old[1])
                self.assertEqual(self.receipt('W', session), withdrawn)

    def test_stepwise_replay(self):
        self.prepare()
        a = self.adjust('A', -10)
        local = self.adjust('L', 30, onsite=True)
        c = self.adjust('C', -20)
        self.assertEqual([row['level'] for row in (a, local, c)], [70, 100, 80])
        result = self.withdraw()
        self.assertEqual((result['level'], result['seq']), (80, 5))
        self.assertEqual(self.current()['level'], 80)
        self.assertEqual(self.receipt('A'), a)
        self.assertEqual(self.first('L', source='local'), local)
        self.assertEqual(self.receipt('C'), c)
        again = self.withdraw('W2')
        self.assertEqual((again['level'], again['seq']), (80, 6))

    def test_target_scope(self):
        for fixture in ('F1', 'F2'):
            self.post('/fixture', fixture=fixture, label=fixture)
        edition = self.make_edition({'F1': 80, 'F2': 20})
        self.post('/open', session='R1', edition=edition['edition'])
        self.adjust('A', 30, fixture='F2')
        self.adjust('L', 10, onsite=True)
        previous = [self.current(), self.current(fixture='F2')]
        self.reject(404, 'unknown_target', self.withdraw, 'W1', 'A')
        self.reject(404, 'unknown_target', self.withdraw, 'W2', 'L')
        self.reject(404, 'unknown_target', self.withdraw, 'W3', 'C')
        self.assertEqual([self.current(), self.current(fixture='F2')], previous)
        self.reject(404, 'unknown_receipt', self.receipt, 'W3')
        self.adjust('C', -10)
        self.reject(404, 'unknown_target', self.withdraw, 'W3', 'C')
        self.reject(409, 'request_conflict', self.withdraw, 'W3', 'A')

    def test_admission_boundary(self):
        self.target_history(10)
        gate = self.relay.arm(Gate('/command', matches={'action': 'W'}, hold=True))
        with ThreadPoolExecutor(max_workers=1) as workers:
            future = workers.submit(self.withdraw)
            try:
                self.assertTrue(gate.entered.wait(8))
                local = self.adjust('M', -5, onsite=True)
                self.assertEqual((local['level'], local['seq']), (85, 5))
            finally:
                gate.release.set()
            result = future.result(timeout=10)
        self.assertEqual((result['level'], result['seq']), (75, 6))
        self.assertEqual((self.current()['level'], self.current()['seq']), (75, 6))

    def test_late_local_and_lost_reply(self):
        old = self.target_history(10)
        gate = self.relay.arm(Gate('/command', matches={'action': 'W'}, hold=True, drop_reply=True))
        with ThreadPoolExecutor(max_workers=1) as workers:
            future = workers.submit(self.withdraw)
            try:
                self.assertTrue(gate.entered.wait(8))
                local = self.adjust('M', -5, onsite=True)
                self.assertEqual((local['level'], local['seq']), (85, 5))
            finally:
                gate.release.set()
            pending = future.result(timeout=10)
        self.assertTrue(gate.committed_reply.is_set())
        self.assertEqual(pending, {'status': 'pending', 'session': 'R1', 'action': 'W'})
        actual = self.first('W')
        self.assertEqual((actual['level'], actual['seq']), (75, 6))
        later = self.adjust('J', 4, onsite=True)
        self.assertEqual((later['level'], later['seq']), (79, 7))
        self.restart()
        self.reject(409, 'request_conflict', self.withdraw, 'W', 'C')
        replayed = self.withdraw()
        self.assertEqual(replayed, {'status': 'applied', **actual})
        self.assertEqual(self.receipt('W'), replayed)
        self.assertEqual(self.first('W'), actual)
        current = self.current()
        self.assertEqual((current['level'], current['seq'], current['action']), (79, 7, 'J'))
        self.assertEqual(self.receipt('A'), old[0])
        self.assertEqual(self.first('L', source='local'), old[1])
        self.assertEqual(self.receipt('C'), old[2])
        self.assertEqual(self.first('M', source='local'), local)
        closed = self.post('/close', session='R1')
        report = self.get('/report', report=closed['report'])
        self.assertEqual([(row['seq'], row['action'], row['level']) for row in report['timeline']],
                         [(1, 'F1', 80), (2, 'A', 100), (3, 'L', 100), (4, 'C', 90),
                          (5, 'M', 85), (6, 'W', 75), (7, 'J', 79)])

    def test_receipt_query_recovers_lost_reply(self):
        self.target_history(10)
        gate = self.relay.arm(Gate('/command', matches={'action': 'W'}, drop_reply=True))
        self.assertEqual(self.withdraw()['status'], 'pending')
        self.assertTrue(gate.committed_reply.is_set())
        self.adjust('J', 4, onsite=True)
        self.restart()
        receipt = self.receipt('W')
        self.assertEqual((receipt['status'], receipt['level'], receipt['seq']), ('applied', 80, 5))
        self.assertEqual((self.current()['level'], self.current()['seq']), (84, 6))
        self.assertEqual(self.withdraw(), receipt)
