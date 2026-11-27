from tests.support import Gate, RehearsalCase


class TestPrepare(RehearsalCase):
    def test_open_fixed_scene(self):
        self.post('/fixture', fixture='F1', label='前区灯')
        first = self.make_edition({'F1': 80})
        second = self.make_edition({'F1': 30})
        self.assertNotEqual(first['edition'], second['edition'])
        opened = self.post('/open', session='R1', edition=first['edition'])
        self.assertEqual(opened['edition'], first['edition'])
        self.assertEqual(opened['bindings'], {'F1': 80})
        self.assertEqual((self.current()['level'], self.current()['seq']), (80, 1))
        self.assertEqual(self.get('/edition', edition=first['edition']), first)

    def test_reject_out_of_range(self):
        self.post('/fixture', fixture='F1', label='前区灯')
        first = self.make_edition({'F1': 80})
        self.post('/draft', scene='opening', levels={'F1': 101})
        self.reject(400, 'invalid_initial_level', self.post, '/proof', scene='opening')
        self.reject(404, 'unknown_edition', self.get, '/edition', edition='E2')
        self.post('/open', session='R1', edition=first['edition'])
        self.assertEqual(self.current()['level'], 80)
        self.assertEqual(self.make_edition({'F1': 30})['edition'], 'E2')

    def test_invalid_scene(self):
        self.post('/fixture', fixture='F1', label='前区灯')
        good = self.make_edition({'F1': 80})
        cases = [({}, 'empty_scene'), ({'F2': 40}, 'unknown_scene_fixture'),
                 ({'F1': None}, 'invalid_initial_level'), ({'F1': True}, 'invalid_initial_level'),
                 ({'F1': 40.0}, 'invalid_initial_level'), ({'F1': '40'}, 'invalid_initial_level')]
        for levels, code in cases:
            with self.subTest(levels=levels):
                self.post('/draft', scene='opening', levels=levels)
                self.reject(400, code, self.post, '/proof', scene='opening')
        self.reject(400, 'invalid_levels', self.post, '/draft', scene='opening')
        self.assertEqual(self.get('/edition', edition=good['edition']), good)
        self.reject(404, 'unknown_edition', self.get, '/edition', edition='E2')

    def test_open_guard(self):
        self.post('/fixture', fixture='F2', label='侧区灯')
        original = self.prepare()
        other = self.make_edition({'F2': 40, 'F1': 30})
        self.reject(404, 'unknown_edition', self.post, '/open', session='R1', edition='E99')
        self.reject(409, 'session_edition_conflict', self.post, '/open',
                    session='R1', edition=other['edition'])
        self.assertEqual(self.current(), original['initial'][0])
        opened = self.post('/open', session='R2', edition=other['edition'])
        order = [(row['fixture'], row['seq'], row['level']) for row in opened['initial']]
        self.assertEqual(order, [('F1', 1, 30), ('F2', 2, 40)])

    def test_bootstrap_repeat(self):
        opened = self.prepare()
        original = self.get('/edition', edition=opened['edition'])
        changed = self.make_edition({'F1': 30})
        local = self.adjust('L', -5, onsite=True)
        for _ in range(2):
            self.restart()
            self.assertEqual(self.get('/fixture', fixture='F1'), {'fixture': 'F1', 'label': '前区灯'})
            self.assertEqual(self.get('/draft', scene='opening')['levels'], {'F1': 30})
            self.assertEqual(self.get('/edition', edition=original['edition']), original)
            self.assertEqual(self.get('/edition', edition=changed['edition']), changed)
            self.assertEqual(self.current()['seq'], local['seq'])
            self.assertEqual(self.current()['level'], 75)
            self.assertEqual(self.post('/open', session='R1', edition=original['edition']), opened)
        self.assertEqual(self.make_edition({'F1': 25})['edition'], 'E3')

    def test_open_resumes_after_lost_confirmation(self):
        self.post('/fixture', fixture='F1', label='前区灯')
        edition = self.make_edition({'F1': 80})['edition']
        gate = self.relay.arm(Gate('/initialize', drop_reply=True))
        self.reject(503, 'opening_unconfirmed', self.post, '/open', session='R1', edition=edition)
        self.assertTrue(gate.committed_reply.is_set())
        self.reject(409, 'session_not_open', self.adjust, 'A', 10)
        local = self.adjust('L', -5, onsite=True)
        self.restart()
        opened = self.post('/open', session='R1', edition=edition)
        self.assertEqual((opened['initial'][0]['seq'], opened['initial'][0]['level']), (1, 80))
        self.assertEqual((self.current()['seq'], self.current()['level']), (local['seq'], 75))
