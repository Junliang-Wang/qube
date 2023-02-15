import unittest

from qcodes import Parameter
from qcodes import validators as vals

from qube.measurement import Controls
from qube.drivers.NEEL_DAC import Virtual_NEEL_DAC, NEEL_DAC_Sequencer

V = Virtual_NEEL_DAC
V.print_order = False


class Test_Virtual_NEEL_DAC(unittest.TestCase):
    def test_panels(self):
        l = [1, 2, 4]

        dac = V(
            name='test_panels',
            bitfile='bitfile',
            address='address',
            panels=l,
            delay_between_steps=1,
        )

        dac.set_panels(l)
        panels = dac.get_panels()
        self.assertEqual(panels, l)
        for li in l:
            self.assertTrue(hasattr(dac, f'p{li}'))
        p1 = dac.p1
        self.assertTrue(p1.panel_number, 1)
        self.assertTrue(len(p1.submodules), dac.max_channels)
        for i in range(dac.max_channels):
            self.assertTrue(hasattr(p1, f'c{i}'))

        dac.max_panels = 8
        self.assertRaises(ValueError, dac.set_panels, [10])

    def test_channels(self):
        dac = V(
            name='test_channels',
            bitfile='bitfile',
            address='address',
            panels=[1, 2, 4],
            delay_between_steps=1,
        )

        p1 = dac.p1
        for i in range(dac.max_channels):
            self.assertTrue(hasattr(p1, f'c{i}'))
        c1 = dac.p1.c1
        self.assertTrue(c1.panel, 1)
        self.assertTrue(c1.channel, 1)
        self.assertTrue(isinstance(c1.v, Parameter))

    def test_values(self):
        vi = -0.5
        l = [1, 2, 4]
        dac = V(
            name='test_values',
            bitfile='bitfile',
            address='address',
            panels=l,
            delay_between_steps=1,
        )

        dac.set_value(panel=1, channel=2, value=vi)
        self.assertEqual(dac.p1.c2.v(), vi)

        # dac.move_all_to(vi)
        # npt.assert_equal(dac.get_values(precision=4), np.ones((len(l),dac.max_channels))*vi)


class Test_NEEL_DAC_Sequencer(unittest.TestCase):
    def test_defaults(self):
        dac = V(
            name='test_defaults',
            bitfile='bitfile',
            address='address',
            panels=[1, 2, 4],
            delay_between_steps=1,
        )
        seq = dac.sequencer
        self.assertTrue(isinstance(seq, NEEL_DAC_Sequencer))

        self.assertEqual(len(seq.slots), 1)
        self.assertEqual(len(seq.orders), 1)
        self.assertEqual(len(seq.used_channels), 0)
        self.assertTrue('end_presequence' in seq.default_flags.keys())
        self.assertTrue('end_sequence' in seq.default_flags.keys())
        self.assertEqual(seq.flags, seq.default_flags)
        self.assertEqual(seq.orders[0], ['trigger', [0, 0, 0, 0, 0]])
        self.assertEqual(seq.n_loop, 1)

        seq.set_ramp_mode(False)
        self.assertFalse(seq.ramp_mode())
        seq.set_sample_count(3)
        self.assertEqual(seq.sample_count(), 3)

    def test_add_channel(self):
        dac = V(
            name='test_add_channel',
            bitfile='bitfile',
            address='address',
            panels=[1, 2, 4],
            delay_between_steps=1,
        )
        seq = dac.sequencer

        # Check Parameter
        param = dac.p1.c1.v
        name, index = seq.add_channel(param)
        self.assertEqual(name, param.instrument.name)
        self.assertEqual(index, 0)
        self.assertEqual(len(seq.used_channels), 1)
        self.assertEqual(seq.used_channels[0], 'p1.c1')
        self.assertEqual(seq.orders_ref['p1.c1'], 0)
        self.assertEqual(seq.orders_ref[name], 0)

        # Check DelegateParameter
        controls = Controls('controls')
        param = controls.add_control('param', source=dac.p2.c2.v)
        name, index = seq.add_channel(param)
        self.assertEqual(name, param.name)
        self.assertEqual(index, 1)
        self.assertEqual(len(seq.used_channels), 2)
        self.assertEqual(seq.used_channels[1], 'p2.c2')
        self.assertEqual(seq.orders_ref['p2.c2'], 1)
        self.assertEqual(seq.orders_ref[param.name], 1)

        # Check not valid channel
        self.assertRaises(ValueError, seq.add_channel, 'ramdon')

        # Reset channels
        seq._reset_channels()
        self.assertEqual(len(seq.used_channels), 0)
        self.assertEqual(len(seq.orders), 1)

        # Check max number of channels
        seq.used_channels = list(range(seq.n_channels))
        self.assertRaises(ValueError, seq.add_channel, param)

    def test_slots(self):
        dac = V(
            name='test_slots',
            bitfile='bitfile',
            address='address',
            panels=[1, 2, 4],
            delay_between_steps=1,
        )
        seq = dac.sequencer

        controls = Controls('controls')
        g1 = controls.add_control(
            'g1',
            source=dac.p1.c1.v,
            label='g1',
            unit='V',
            vals=vals.Numbers(-2, 1),
        )

        s1 = seq.add_slot_trigger([0, 0, 0, 0, 0])
        self.assertEqual(len(seq.slots), 2)
        self.assertEqual(len(seq.orders), 2)
        self.assertTrue(isinstance(s1, Parameter))
        self.assertEqual(seq.slots[s1.name], s1)
        self.assertEqual(seq.orders[1], ['trigger', [0, 0, 0, 0, 0]])

        s2 = seq.add_slot_wait(1)  # ms
        self.assertEqual(len(seq.slots), 3)
        self.assertEqual(len(seq.orders), 3)
        self.assertTrue(isinstance(s2, Parameter))
        self.assertEqual(seq.slots[s2.name], s2)
        self.assertEqual(seq.orders[2], ['wait', 1])

        g1(-0.5)
        s3 = seq.add_slot_move(g1, -0.1, alias='g1_load', relative=True)
        self.assertEqual(s3.name, 'g1_load')
        self.assertEqual(seq.slots['g1_load'], s3)
        self.assertEqual(seq.orders[3], ['g1', -0.6])
        self.assertEqual(seq._raw_values[3], -0.1)

        s4 = seq.add_slot_move(g1, -0.1, alias='g1_unload', relative=False)
        self.assertEqual(seq.orders[4], ['g1', -0.1])
        self.assertEqual(seq._raw_values[4], +0.4)

    def test_correct_jump(self):
        dac = V(
            name='test_correct_jump',
            bitfile='bitfile',
            address='address',
            panels=[1, 2, 4],
            delay_between_steps=1,
        )
        seq = dac.sequencer

        """
        NO jump order / NO loop / NO end_presequence flag --> add end order
        """
        seq.reset()
        seq.add_slot_wait(1)  # ms
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.repeat_sequence(n=1)
        self.assertEqual(seq.get_last_slot_index(), 2)

        seq.start()
        self.assertEqual(seq.get_last_slot_index(), 3)
        self.assertEqual(seq.orders[3], ['jump', 3])
        self.assertEqual(seq.flags['end_sequence'], 4)

        """
        YES jump order (end) / NO loop / NO end_presequence flag --> no change
        """
        seq.reset()
        seq.add_slot_wait(1)  # ms
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.add_slot_end()
        seq.repeat_sequence(n=1)
        self.assertEqual(seq.get_last_slot_index(), 3)

        seq.start()
        self.assertEqual(seq.get_last_slot_index(), 3)
        self.assertEqual(seq.orders[3], ['jump', 3])
        self.assertEqual(seq.flags['end_sequence'], 4)

        """
        YES jump order (not end) / NO loop / NO end_presequence flag --> change jump value to last index
        """
        seq.reset()
        seq.add_slot_wait(1)  # ms
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.add_slot_jump(1)
        seq.repeat_sequence(n=1)
        self.assertEqual(seq.get_last_slot_index(), 3)

        seq.start()
        self.assertEqual(seq.get_last_slot_index(), 3)
        self.assertEqual(seq.orders[3], ['jump', 3])
        self.assertEqual(seq.flags['end_sequence'], 4)

        """
        YES jump order (end) + extra slots/ NO loop / NO end_presequence flag --> remove extra slots
        """
        seq.reset()
        seq.add_slot_wait(1)  # ms
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.add_slot_end()
        seq.add_slot_jump(0)
        seq.add_slot_jump(1)
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.repeat_sequence(n=1)
        self.assertEqual(seq.get_last_slot_index(), 6)

        seq.start()
        self.assertEqual(seq.get_last_slot_index(), 3)
        self.assertEqual(seq.orders[-1], ['jump', 3])
        self.assertEqual(seq.flags['end_sequence'], 4)

        """
        NO jump order / YES loop / NO end_presequence flag --> add jump to 0
        """
        seq.reset()
        seq.add_slot_wait(1)  # ms
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.repeat_sequence(n=2)
        self.assertEqual(seq.get_last_slot_index(), 2)

        seq.start()  # add jump order
        self.assertEqual(seq.get_last_slot_index(), 3)
        self.assertEqual(seq.orders[-1], ['jump', 0])
        self.assertEqual(seq.flags['end_presequence'], 0)

        """
        NO jump order / YES loop / YES end_presequence flag --> add jump to end_presequence
        """
        seq.reset()
        seq.add_slot_wait(1)  # ms
        seq.flag_end_presequence()  # index = 2
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.repeat_sequence(n=2)
        self.assertEqual(seq.get_last_slot_index(), 2)
        self.assertEqual(seq.flags['end_presequence'], 2)

        seq.start()
        self.assertEqual(seq.get_last_slot_index(), 3)
        self.assertEqual(seq.orders[-1], ['jump', 2])
        self.assertEqual(seq.flags['end_presequence'], 2)

        """
        NO jump order / NO loop / YES end_presequence flag --> add jump to last index
        """
        # Check jump value WITHOUT repetitions and WITH pre_sequence flag
        seq.reset()
        seq.add_slot_wait(1)  # ms
        seq.flag_end_presequence()
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.repeat_sequence(n=1)
        self.assertEqual(seq.get_last_slot_index(), 2)
        self.assertEqual(seq.flags['end_presequence'], 2)

        seq.start()
        self.assertEqual(seq.get_last_slot_index(), 3)
        self.assertEqual(seq.orders[-1], ['jump', 3])
        self.assertEqual(seq.flags['end_presequence'], 2)

        """
        YES jump order (end) / YES loop / YES end_presequence flag --> update jump value to end_presequence
        """
        seq.reset()
        seq.add_slot_wait(1)  # ms
        seq.flag_end_presequence()
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.add_slot_end()
        seq.repeat_sequence(n=2)
        self.assertEqual(seq.flags['end_presequence'], 2)

        seq.start()
        self.assertEqual(seq.orders[-1], ['jump', 2])

        """
        YES jump order (not end) / YES loop / YES end_presequence flag --> update end_presequence flag
        """
        seq.reset()
        seq.add_slot_wait(1)  # ms
        seq.flag_end_presequence()
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.add_slot_jump(1)
        seq.repeat_sequence(n=2)
        self.assertEqual(seq.flags['end_presequence'], 2)

        seq.start()
        self.assertEqual(seq.orders[-1], ['jump', 1])
        self.assertEqual(seq.flags['end_presequence'], 1)

        """
        YES jump order (not end) / YES loop / NO end_presequence flag --> update end_presequence flag
        """
        # Check jump value WITH repetitions, WITHOUT pre_sequence flag and manual jump
        seq.reset()
        seq.add_slot_wait(1)  # ms
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.add_slot_jump(2)
        seq.repeat_sequence(n=2)
        self.assertEqual(seq.flags['end_presequence'], 0)

        seq.start()  # it updates end_presequence
        self.assertEqual(seq.orders[-1], ['jump', 2])
        self.assertEqual(seq.flags['end_presequence'], 2)

    def test_sample_count_ramp(self):
        dac = V(
            name='test_sample_count',
            bitfile='bitfile',
            address='address',
            panels=[1, 2, 4],
            delay_between_steps=1,
        )
        seq = dac.sequencer
        seq.reset()
        seq.ramp_mode(True)
        seq.sample_time(1)
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.add_slot_move(dac.p2.c2.v, 0.0)
        w = seq.add_slot_wait(0.5)
        seq.add_slot_trigger([0, 0, 0, 0, 0])
        seq.add_slot_trigger([0, 1, 0, 0, 0])
        seq.add_slot_end()

        """
        NO loop / NO end_presequence flag / NO long wait 
        """
        w(0.5)
        seq.repeat_sequence(n=1)
        seq.start()
        self.assertEqual(seq.sample_count(), 2)

        """
        NO loop / NO end_presequence flag / YES long wait
        """
        w(1.5)
        seq.repeat_sequence(n=1)
        seq.start()
        self.assertEqual(seq.sample_count(), 3)

        """
        YES loop / NO end_presequence flag / NO long wait
        """
        w(0.5)
        seq.repeat_sequence(n=10)
        seq.start()
        self.assertEqual(seq.sample_count(), 2 * 10)

        """
        YES loop (infinite) / NO end_presequence flag / NO long wait
        """
        w(0.5)
        seq.repeat_infinite()
        seq.start()
        self.assertEqual(seq.sample_count(), 0)

        """
        YES loop / YES end_presequence flag / NO long wait
        """
        seq.reset()
        seq.ramp_mode(True)
        seq.sample_time(1)
        seq.add_slot_trigger([0, 0, 0, 0, 0])
        seq.add_slot_trigger([0, 1, 0, 0, 0])
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.add_slot_move(dac.p2.c2.v, 0.0)
        w = seq.add_slot_wait(0.5)
        seq.flag_end_presequence()
        seq.add_slot_move(dac.p1.c1.v, 0.0)
        seq.add_slot_move(dac.p2.c2.v, 0.0)
        seq.add_slot_end()

        seq.repeat_sequence(n=10)
        seq.start()
        self.assertEqual(seq.sample_count(), 2 + 2 * 10)


# TODO
# class Test_NEEL_DAC_LockIn(unittest.TestCase):
#     def test_defaults(self):
#         dac = V(
#             name='test_defaults',
#             bitfile='bitfile',
#             address='address',
#             panels=[1, 2, 4],
#             delay_between_steps=1,
#         )
#         li = dac.lockin
#         # self.assertTrue(isinstance(seq, NEEL_DAC_Sequencer))
#         #
#         # self.assertEqual(len(seq.slots), 0)
#         # self.assertEqual(len(seq.used_channels), 0)
#         # self.assertEqual(len(seq.orders), 0)
#         # seq.set_ramp_mode(False)
#         # self.assertFalse(seq.ramp_mode())
#         # seq.set_sample_count(3)
#         # self.assertEqual(seq.sample_counts(), 3)


if __name__ == '__main__':
    unittest.main()
