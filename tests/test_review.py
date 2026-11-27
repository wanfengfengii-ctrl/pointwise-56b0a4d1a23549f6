from concurrent.futures import ThreadPoolExecutor

from tests.support import Gate, RehearsalCase


class TestReview(RehearsalCase):
    def test_close_and_read_back(self):
        self.prepare(30)
        self.adjust('A', 20)
        self.adjust('L', -5, onsite=True)
        closed = self.post('/close', session='R1')
        report = self.get('/report', report=closed['report'])
        self.assertEqual([(item['seq'], item['action'], item['source'], item['level'])
                          for item in report['timeline']],
                         [(1, 'F1', 'initial', 30), (2, 'A', 'desk', 50), (3, 'L', 'local', 45)])
        self.reject(409, 'session_closed', self.adjust, 'late', 4, onsite=True)
        self.assertEqual(self.get('/report', report=closed['report']), report)
        self.assertEqual(self.post('/close', session='R1'), closed)

    def test_close_fence(self):
        self.prepare()
        old = self.adjust('L', -5, onsite=True)
        closed = self.post('/close', session='R1')
        report = self.get('/report', report=closed['report'])
        current = self.current()
        self.reject(409, 'session_closed', self.adjust, 'late', 3, onsite=True)
        self.reject(409, 'session_not_open', self.adjust, 'late', 3)
        self.assertEqual(self.adjust('L', -5, onsite=True), old)
        self.assertEqual(self.current(), current)
        self.assertEqual(self.get('/report', report=closed['report']), report)

    def test_resume_close(self):
        self.prepare()
        self.adjust('A', -4)
        gate = self.relay.arm(Gate('/cut', hold=True, drop_before=True))
        with ThreadPoolExecutor(max_workers=1) as workers:
            future = workers.submit(self.post, '/close', session='R1')
            try:
                self.assertTrue(gate.entered.wait(8))
                self.reject(404, 'unknown_report', self.get, '/report', report='report-R1')
                self.reject(409, 'session_closed', self.adjust, 'late', 2, onsite=True)
            finally:
                gate.release.set()
            self.reject(503, 'close_unconfirmed', future.result, timeout=10)
        self.restart()
        closed = self.post('/close', session='R1')
        self.assertEqual(self.post('/close', session='R1'), closed)
        report = self.get('/report', report=closed['report'])
        self.assertEqual(report['cutoff'], 2)
        self.assertEqual([row['level'] for row in report['timeline']], [80, 76])

    def test_archive_history(self):
        old = self.target_history(10)
        withdrawn = self.withdraw()
        closed = self.post('/close', session='R1')
        report = self.get('/report', report=closed['report'])
        self.assertEqual(report['cutoff'], 5)
        self.assertEqual([row['level'] for row in report['timeline']], [80, 100, 100, 90, 80])
        self.assertEqual([(row['seq'], row['action'], row['source'], row['target'])
                          for row in report['sources']],
                         [(1, 'F1', 'initial', None), (2, 'A', 'desk', None),
                          (3, 'L', 'local', None), (4, 'C', 'desk', None), (5, 'W', 'desk', 'A')])
        new = self.make_edition({'F1': 30})
        self.assertNotEqual(new['edition'], report['edition'])
        self.restart()
        self.assertEqual(self.post('/close', session='R1'), closed)
        self.assertEqual(self.get('/report', report=closed['report']), report)
        self.assertEqual(self.receipt('A'), old[0])
        self.assertEqual(self.withdraw(), withdrawn)
