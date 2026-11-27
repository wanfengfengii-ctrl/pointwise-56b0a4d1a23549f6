"""两次错光修复后的回归用例。

覆盖两类事故并补齐受影响的语义：
1. 撤去控台调光时，饱和处与零增量的现场动作仍按原始增量参与重放；
2. 撤去在途期间受理的现场动作不会被随后到达的撤去抹掉；
3. 控台失联时灯台仍可就地调光，两端各自提交，原号续办、同号异参拒绝；
4. 旧首执与复盘保留实际实显、原号与原始增量。
"""
from concurrent.futures import ThreadPoolExecutor

from tests.support import Gate, RehearsalCase


class IncidentFixCase(RehearsalCase):
    def test_withdrawal_keeps_saturated_local_delta(self):
        # 事故一：初值 80，控台 +30、现场 +10（饱和实显仍 100）、控台 -10，
        # 撤去 +30 后应为 80 而不是 70，且现场首执保留原始增量 +10。
        self.prepare()
        receipts = [self.adjust('A', 30),
                    self.adjust('L', 10, onsite=True),
                    self.adjust('C', -10)]
        self.assertEqual([row['level'] for row in receipts], [100, 100, 90])
        withdrawn = self.withdraw()
        current = self.current()
        self.assertEqual((withdrawn['status'], withdrawn['action'], withdrawn['seq']),
                         ('applied', 'W', 5))
        self.assertEqual((withdrawn['level'], current['level']), (80, 80))
        self.assertEqual((current['action'], current['seq']), ('W', 5))
        # 原始增量与原号首执始终保留，复领不改变现值。
        self.assertEqual(self.receipt('A'), receipts[0])
        self.assertEqual(self.receipt('A')['delta'], 30)
        local_first = self.first('L', source='local')
        self.assertEqual((local_first['delta'], local_first['level'], local_first['seq']),
                         (10, 100, 3))
        self.assertEqual(self.receipt('C')['delta'], -10)
        self.assertEqual(self.withdraw(), withdrawn)
        self.assertEqual(self.current()['level'], 80)

    def test_zero_delta_local_adjustment_is_retained(self):
        # 亮度没变也要保留原增量：现场 0 级动作实显不变，但仍是一笔具名实显，
        # 撤去控台 +30 后按 80 + 0 - 10 重放为 70。
        self.target_history(0)
        zero = self.first('L', source='local')
        self.assertEqual((zero['delta'], zero['level']), (0, 100))
        withdrawn = self.withdraw()
        self.assertEqual((withdrawn['level'], withdrawn['seq']), (70, 5))
        self.assertEqual(self.current()['level'], 70)

    def test_withdrawal_in_flight_keeps_interim_local_adjustment(self):
        # 事故二：撤去尚在途中，现场先加 5；撤去受理时必须把这 5 级计入。
        self.prepare(60)
        self.adjust('A', 20)
        self.adjust('B', -10)
        gate = self.relay.arm(Gate('/command', matches={'action': 'W'}, hold=True))
        with ThreadPoolExecutor(max_workers=1) as workers:
            future = workers.submit(self.withdraw)
            try:
                self.assertTrue(gate.entered.wait(8))
                local = self.adjust('M', 5, onsite=True)
                self.assertEqual((local['level'], local['seq'], local['delta']), (75, 4, 5))
            finally:
                gate.release.set()
            result = future.result(timeout=10)
        self.assertEqual((result['status'], result['action'], result['seq']),
                         ('applied', 'W', 5))
        self.assertEqual((result['level'], self.current()['level']), (55, 55))
        # 60 + 20 - 10 + 5，撤去只排除 A：60 - 10 + 5 = 55。
        self.assertEqual(self.first('M', source='local')['delta'], 5)

    def test_local_dimming_survives_console_disconnect_and_withdrawal(self):
        # 控台失联时灯台仍可就地调光；控台恢复后撤去仍尊重现场原增量。
        self.prepare()
        self.console.stop()
        local = self.adjust('L', 30, onsite=True)
        self.assertEqual((local['level'], local['seq'], local['delta']), (100, 2, 30))
        self.start_console()
        desk = self.adjust('A', -20)
        self.assertEqual((desk['level'], desk['seq'], desk['delta']), (80, 3, -20))
        withdrawn = self.withdraw()
        # 80（初值）+ 30（现场，饱和过但保留原量）- 撤去 A，只剩现场：80 + 30 截到 100。
        self.assertEqual((withdrawn['level'], withdrawn['seq']), (100, 4))
        self.assertEqual(self.current()['level'], 100)
        self.assertEqual(self.first('L', source='local'), local)

    def test_receipt_rules_and_handoff_report_after_fix(self):
        # 待查按原号续办；同号同参只领当时亮度和序号，同号异参拒绝；
        # 旧首执与复盘保留实际实显及出处。
        old = self.target_history(10)
        withdrawn = self.withdraw()
        self.reject(409, 'request_conflict', self.withdraw, 'W', 'C')
        self.assertEqual(self.withdraw(), withdrawn)
        closed = self.post('/close', session='R1')
        report = self.get('/report', report=closed['report'])
        self.assertEqual([(row['seq'], row['action'], row['source'], row['level'])
                          for row in report['timeline']],
                         [(1, 'F1', 'initial', 80), (2, 'A', 'desk', 100),
                          (3, 'L', 'local', 100), (4, 'C', 'desk', 90),
                          (5, 'W', 'desk', 80)])
        self.assertEqual([(row['source'], row['action'], row['target'])
                          for row in report['sources']],
                         [('initial', 'F1', None), ('desk', 'A', None),
                          ('local', 'L', None), ('desk', 'C', None),
                          ('desk', 'W', 'A')])
        # 封轮后原册与原号首执仍按实际实显读取。
        self.assertEqual(self.receipt('A'), old[0])
        self.assertEqual(self.first('L', source='local'), old[1])
        self.assertEqual(self.post('/close', session='R1'), closed)
