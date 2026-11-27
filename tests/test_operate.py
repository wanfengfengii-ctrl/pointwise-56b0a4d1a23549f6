from tests.support import Gate, RehearsalCase


class TestOperate(RehearsalCase):
    def test_adjust_and_read(self):
        self.prepare(30)
        first = self.adjust('A', 20)
        onsite = self.adjust('L', -5, onsite=True)
        self.assertEqual((first['level'], first['seq']), (50, 2))
        self.assertEqual((onsite['level'], onsite['seq']), (45, 3))
        self.assertEqual(self.current()['level'], 45)
        self.assertEqual(self.receipt('A'), first)
        self.assertEqual(self.adjust('A', 20), first)
        self.assertEqual(self.current()['seq'], 3)

    def test_local_while_disconnected(self):
        self.prepare()
        self.console.stop()
        actual = self.adjust('L', 30, onsite=True)
        self.assertEqual((actual['level'], actual['seq'], actual['delta']), (100, 2, 30))
        self.assertEqual(self.current()['action'], 'L')
        self.start_console()
        later = self.adjust('A', -8)
        self.assertEqual((later['level'], later['seq']), (92, 3))
        self.assertEqual(self.first('L', source='local'), actual)

    def test_binding_scope(self):
        self.prepare()
        previous = self.current()
        self.reject(404, 'unknown_binding', self.adjust, 'L', 10, fixture='F2', onsite=True)
        self.reject(404, 'unknown_binding', self.adjust, 'A', 10, fixture='F2')
        self.reject(404, 'unknown_binding', self.current, fixture='F2')
        self.assertEqual(self.current(), previous)

    def test_conflicting_request(self):
        self.prepare(30)
        first = self.adjust('A', 20)
        current = self.current()
        self.assertEqual(self.adjust('A', 20), first)
        self.reject(409, 'request_conflict', self.adjust, 'A', 21)
        self.reject(409, 'request_conflict', self.withdraw, 'A', 'A')
        self.assertEqual(self.receipt('A'), first)
        self.assertEqual(self.current(), current)

    def test_unaccepted_request_can_resume(self):
        self.prepare(30)
        gate = self.relay.arm(Gate('/command', matches={'action': 'A'}, drop_before=True))
        pending = self.adjust('A', 20)
        self.assertTrue(gate.entered.is_set())
        self.assertFalse(gate.committed_reply.is_set())
        self.assertEqual(pending, {'status': 'pending', 'session': 'R1', 'action': 'A'})
        self.assertEqual(self.receipt('A'), pending)
        self.reject(404, 'unknown_emission', self.first, 'A')
        self.adjust('L', -5, onsite=True)
        self.restart()
        first = self.adjust('A', 20)
        self.assertEqual((first['level'], first['seq']), (45, 3))
        self.assertEqual(self.receipt('A'), first)
