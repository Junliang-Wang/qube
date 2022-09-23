import unittest

from qcodes import Parameter
from qcodes import validators as vals

from qube import Controls
from qube.drivers.NEEL_DAC_JL import Virtual_NEEL_DAC, NEEL_DAC_Sequencer

#
# dac = Virtual_NEEL_DAC(
#     name='DAC',
#     bitfile='bitfile',
#     address='address',
#     panels=[1, 2, 3, 4],
#     delay_between_steps=1,
#     # initial_value=0,
# )
# dac.print_order = False
#
# controls = Controls('controls')
# TRR = controls.add_control(
#     'TRR',
#     source=dac.p2.c2.v,
#     label='TRR',
#     unit='V',
#     initial_value=-1.20,
#     vals=vals.Numbers(-2.2, 0.3),
# )
#
# TRC = controls.add_control(
#     'TRC',
#     source=dac.p3.c3.v,
#     label='TRC',
#     unit='V',
#     initial_value=-1.30,
#     vals=vals.Numbers(-2.2, 0.3),
# )
#
# seq = dac.sequencer
# seq.set_ramp_mode(False)
# # seq.set_channels([dac.p1.c1, gate1, dac.p3.c3.v, 'random'])
# # print(seq.orders_ref)
# seq.add_trigger_slot([0, 0, 0, 0, 0])
# seq.add_wait_slot(1)  # ms
# seq.add_trigger_slot([0, 1, 0, 0, 0])  # trigger ADC
# TRR_load = seq.add_move_slot(TRR, -0.1, alias='TRR_load', relative=False)
# TRC_load = seq.add_move_slot(TRC, -0.2, alias='TRC_load', relative=True)
# p4c4 = seq.add_move_slot(dac.p4.c4.v, -0.5, alias='p4c4', relative=True)
# random = seq.add_move_slot(dac.p4.c4.v, -1.0, alias='random', relative=False)
# seq.add_end_slot()


# TRR_back = seq.add_move_slot(TRR, -2.3, alias='TRR_back', relative=False)
# TRC_back = seq.add_move_slot(TRC, 3, alias='TRC_back', relative=True)

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

        self.assertEqual(len(seq.slots), 0)
        self.assertEqual(len(seq.used_channels), 0)
        self.assertEqual(len(seq.orders), 0)
        seq.set_ramp_mode(False)
        self.assertFalse(seq.ramp_mode())
        seq.set_sample_count(3)
        self.assertEqual(seq.sample_counts(), 3)

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
        self.assertEqual(name, param.name)
        self.assertEqual(index, 0)
        self.assertEqual(len(seq.used_channels), 1)
        self.assertEqual(seq.used_channels[0], 'p1.c1')
        self.assertEqual(seq.orders['p1.c1'], 0)
        self.assertEqual(seq.orders[param.name], 0)

        # Check DelegateParameter
        controls = Controls('controls')
        param = controls.add_control('param', source=dac.p2.c2.v)
        name, index = seq.add_channel(param)
        self.assertEqual(name, param.name)
        self.assertEqual(index, 1)
        self.assertEqual(len(seq.used_channels), 2)
        self.assertEqual(seq.used_channels[1], 'p2.c2')
        self.assertEqual(seq.orders['p2.c2'], 1)
        self.assertEqual(seq.orders[param.name], 1)

        # Check not valid channel
        self.assertRaises(ValueError, seq.add_channel, 'ramdon')

        # Reset channels
        seq.reset_channels()
        self.assertEqual(len(seq.used_channels), 0)
        self.assertEqual(len(seq.orders), 0)

        # Check max number of channels
        self.used_channels = list(range(seq.n_channels))
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
            initial_value=0,
            vals=vals.Numbers(-2, 1),
        )
        g2 = controls.add_control(
            'g2',
            source=dac.p2.c2.v,
            label='g2',
            unit='V',
            initial_value=-1.0,
            vals=vals.Numbers(-0.5, 0.5),
        )

        self.assertEqual(len(seq.slots), 0)
        self.assertEqual(len(seq.orders), 0)
        seq.set_sample_count(3)

        s1 = seq.add_slot_trigger([0, 0, 0, 0, 0])
        self.assertEqual(len(seq.slots), 1)
        self.assertEqual(len(seq.orders), 1)
        self.assertEqual(seq.sample_count(), 1)
        self.assertTrue(isinstance(s1, Parameter))
        self.assertEqual(seq.slots[s1.name], s1)
        self.assertEqual(seq.orders[0], ['trigger', [0, 0, 0, 0, 0]])

        s2 = seq.add_slot_wait(1)  # ms
        self.assertEqual(len(seq.slots), 2)
        self.assertEqual(len(seq.orders), 2)
        self.assertEqual(seq.sample_count(), 2)
        self.assertTrue(isinstance(s2, Parameter))
        self.assertEqual(seq.slots[s2.name], s2)
        self.assertEqual(seq.orders[1], ['wait', 1])

        # seq.add_trigger_slot([0, 1, 0, 0, 0])  # trigger ADC
        # TRR_load = seq.add_move_slot(TRR, -0.1, alias='TRR_load', relative=False)
        # TRC_load = seq.add_move_slot(TRC, -0.2, alias='TRC_load', relative=True)
        # p4c4 = seq.add_move_slot(dac.p4.c4.v, -0.5, alias='p4c4', relative=True)
        # random = seq.add_move_slot(dac.p4.c4.v, -1.0, alias='random', relative=False)
        # seq.add_end_slot()

        # TRR_back = seq.add_move_slot(TRR, -2.3, alias='TRR_back', relative=False)
        # TRC_back = seq.add_move_slot(TRC, 3, alias='TRC_back', relative=True)


if __name__ == '__main__':
    unittest.main()
