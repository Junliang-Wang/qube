import unittest
from qube import Controls
from qube.measurement.sweep import Sweep

from qcodes import Parameter, DelegateParameter

v_values = [0, 0, 0]
y_values = [0, 0, 0]


def _set_func(idx, arr):
    def _f(v):
        arr[idx] = v

    return _f


def _get_func(idx, arr):
    def _f():
        return arr[idx]

    return _f


v1 = Parameter(name='v1', label='Voltage', unit='V',
               set_cmd=_set_func(0, v_values), get_cmd=_get_func(0, v_values))
v2 = Parameter(name='v2', label='Voltage', unit='V',
               set_cmd=_set_func(1, v_values), get_cmd=_get_func(1, v_values))
v3 = DelegateParameter(name='delegate_v2', source=v2)

y1 = Parameter(name='y1', label='Current', unit='I',
               set_cmd=None, get_cmd=None)
y2 = Parameter(name='y2', label='Current', unit='I',
               set_cmd=None, get_cmd=None)
y3 = DelegateParameter(name='delegate_y2', source=y2)


class Test_Controls(unittest.TestCase):
    def test_defaults(self):
        c = Controls(name='test_controls')
        self.assertEqual(c.get_controls(), [])
        self.assertEqual(c.get_readouts(), [])
        self.assertEqual(c._move_commands, list())

    def test_add_control(self):
        c = Controls(name='test_controls')

        # add with same name
        p1 = c.add_control(v1.name, source=v1)
        self.assertEqual(p1.name, v1.name)
        self.assertEqual(p1.label, v1.label)
        self.assertEqual(c.get_controls(), [p1.name])
        self.assertEqual(c.get_controls(as_instance=True), [p1])

        # add with different name and label
        p2 = c.add_control('v2_new', source=v2, label='new v2 control')
        self.assertEqual(p2.name, 'v2_new')
        self.assertEqual(p2.label, 'new v2 control')
        self.assertEqual(c.get_controls(), [p1.name, p2.name])
        self.assertEqual(c.get_controls(as_instance=True), [p1, p2])

        # add DelegateParameter
        p3 = c.add_control(v3.name, source=v3)
        self.assertEqual(p3.name, v3.name)
        self.assertEqual(p3.label, v3.label)
        self.assertEqual(c.get_controls()[2], p3.name)
        self.assertEqual(c.get_controls(as_instance=True)[2], p3)

    def test_add_readout(self):
        c = Controls(name='test_controls')

        # add with same name
        p1 = c.add_readout(y1.name, source=y1)
        self.assertEqual(p1.name, y1.name)
        self.assertEqual(p1.label, y1.label)
        self.assertEqual(c.get_readouts(), [y1.name])
        self.assertEqual(c.get_readouts(as_instance=True), [p1])

        # add with different name and label
        p2 = c.add_readout('y2_new', source=y2, label='new y2 readout')
        self.assertEqual(p2.name, 'y2_new')
        self.assertEqual(p2.label, 'new y2 readout')
        self.assertEqual(c.get_readouts(), [p1.name, p2.name])
        self.assertEqual(c.get_readouts(as_instance=True), [p1, p2])

        # add DelegateParameter
        p3 = c.add_readout(y3.name, source=y3)
        self.assertEqual(p3.name, y3.name)
        self.assertEqual(p3.label, y3.label)
        self.assertEqual(c.get_readouts()[2], p3.name)
        self.assertEqual(c.get_readouts(as_instance=True)[2], p3)

    def test_apply(self):
        c = Controls(name='test_controls')
        p1 = c.add_control('v1_new', source=v1)
        p2 = c.add_control('v2_new', source=v2)
        r1 = c.add_readout('y1_new', source=y1)
        r2 = c.add_readout('y2_new', source=y2)

        p1(1)
        self.assertEqual(p1(), 1)
        p2(2)
        self.assertEqual(p2(), 2)

        """
        Apply only one control
        """
        c.apply({'v1_new': 10})  # dict with keys
        self.assertEqual(p1(), 10)
        c.apply({p1: 20})  # dict with instance
        self.assertEqual(p1(), 20)
        c.apply([('v1_new', 30)])  # list of tuple with keys
        self.assertEqual(p1(), 30)
        c.apply([(p1, 40)])  # list of tuple with instances
        self.assertEqual(p1(), 40)

        """
        Apply two controls
        """
        c.apply({'v1_new': 100, 'v2_new': 200})
        self.assertEqual(p1(), 100)
        self.assertEqual(p2(), 200)
        c.apply({'v1_new': 1, p2: 2})
        self.assertEqual(p1(), 1)
        self.assertEqual(p2(), 2)

        """
        Apply one readout --> raise KeyError
        """
        d = {'y1_new': 100}
        self.assertRaises(KeyError, c.apply, d)

        """
        Apply non-defined parameter --> raise KeyError
        """
        d = {'random': 100}
        self.assertRaises(KeyError, c.apply, d)


if __name__ == '__main__':
    unittest.main()
