import unittest

import numpy as np
import numpy.testing as npt
from qcodes import Parameter, DelegateParameter, Measurement

from qube.measurement.sweeper import SweepParameter, Sweeper
from qube.measurement.sweeper import split_sweep_shape, is_qc_param


class TestSweepParameter(unittest.TestCase):
    def test_defaults(self):
        x1 = Parameter('x1', unit='V', set_cmd=None, get_cmd=None)
        f = lambda pts: np.arange(pts)
        sx1 = SweepParameter(x1, value_generator=f, dim=1)
        self.assertEqual(sx1.parameter, x1)
        self.assertEqual(sx1.value_generator, f)
        self.assertEqual(sx1.apply, True)
        self.assertEqual(sx1.refresh, False)
        self.assertEqual(sx1.dim, 1)

    def test_sweep_shape(self):
        x1 = Parameter('x1', unit='V', set_cmd=None, get_cmd=None)
        f = lambda pts: np.arange(pts)
        sx1 = SweepParameter(x1, value_generator=f, dim=1)
        sweep_shape = [2, 3, 4]
        sx1.set_sweep_shape(sweep_shape)
        npt.assert_equal(sx1.sweep_shape, np.array(sweep_shape, dtype=int))
        npt.assert_equal(sx1.values, f(sweep_shape[0]))

        sx1.set_dim(2)
        self.assertEqual(sx1.dim, 2)
        npt.assert_equal(sx1.values, f(sweep_shape[1]))

        self.assertRaises(ValueError, sx1.set_dim, -1)

    def test_instructions(self):
        x1 = Parameter('x1', unit='V', set_cmd=None, get_cmd=None)
        f = lambda pts: np.arange(pts)
        sx1 = SweepParameter(x1, value_generator=f, dim=1)
        sweep_shape = [2, 3, 4]
        sx1.set_sweep_shape(sweep_shape)
        instrs = sx1.get_ordered_instructions()

        sx1.set_dim(2)
        sx1.apply = True
        sx1.refresh = True
        expected = [0, 0, 1, 1, 2, 2] * 4
        for i, instr in enumerate(instrs):
            param, value, change = instr
            self.assertEqual(param, x1)
            self.assertEqual(value, expected[i])
            self.assertEqual(change, True)

        sx1.apply = True
        sx1.refresh = False
        bools = [True, False, True, False, True, False] * 4
        for i, instr in enumerate(instrs):
            param, value, change = instr
            self.assertEqual(change, bools[i])

        sx1.apply = False
        sx1.refresh = False
        for i, instr in enumerate(instrs):
            param, value, change = instr
            self.assertEqual(change, False)

        sx1.apply = False
        sx1.refresh = True
        for i, instr in enumerate(instrs):
            param, value, change = instr
            self.assertEqual(change, False)


class TestFunctions(unittest.TestCase):
    def test_split_sweep_shape(self):
        shape = [2, 3, 4, 5]
        dims_expected = [
            [[], [2 * 3 * 4 * 5, 1, 1]],
            [[1], [1, 2, 3 * 4 * 5]],
            [[2], [2, 3, 4 * 5]],
            [[3], [2 * 3, 4, 5]],
            [[4], [2 * 3 * 4, 5, 1]],
            [[1, 2], [1, 2 * 3, 4 * 5]],
            [[1, 3], [1, 2 * 3 * 4, 5]],
            [[2, 4], [2, 3 * 4 * 5, 1]],
        ]
        for (dims, exp) in dims_expected:
            ns = np.array(split_sweep_shape(shape, dims=dims))
            npt.assert_equal(ns, np.array(exp))

    def test_is_qc_param(self):
        x1 = Parameter('x1', unit='V', set_cmd=None, get_cmd=None)
        x2 = DelegateParameter('name', source=x1)
        arg_expected = [
            [x1, True],
            [x2, True],
            ['test', False],
        ]
        for (arg, b) in arg_expected:
            self.assertEqual(is_qc_param(arg), b)


class TestSweeper(unittest.TestCase):
    def test_defaults(self):
        sw = Sweeper('Sweeper')
        self.assertEqual(sw.name, 'Sweeper')
        self.assertEqual(sw.sweep_parameters, {})
        self.assertEqual(sw.sweep_shape, [])
        self.assertEqual(sw.pre_process_wait, 0)
        self.assertEqual(sw.post_process_wait, 0)
        self.assertEqual(sw.pre_readout_wait, 0)
        self.assertEqual(sw.post_readout_wait, 0)
        self.assertEqual(sw.readouts, [])
        self.assertEqual(sw.start_at, {})
        self.assertEqual(sw.return_to, {})
        self.assertEqual(sw.tracked_parameters, [])
        self.assertEqual(sw.statics, {})
        self.assertEqual(sw.note, '')

    def test_add_sweep(self):
        x1 = Parameter('x1', unit='V', set_cmd=None, get_cmd=None)

        " Sweep dim = 1 with default apply = True, refresh = False "
        sw = Sweeper('Sweeper')
        sw.sweep_linear(x1, 0, -1, dim=1)
        sx1 = sw.sweep_parameters[x1]
        self.assertEqual(sx1.parameter, x1)
        self.assertEqual(sx1.name, x1.name)
        self.assertEqual(sx1.dim, 1)
        sw.set_sweep_shape([3, 4, 5])
        npt.assert_equal(sx1.values, np.linspace(0, -1, 3))

        instrs = sw.get_ordered_instructions()
        expected = list(np.linspace(0, -1, 3)) * 4 * 5
        for i, instr in enumerate(instrs):
            param = list(instr.keys())[0]
            value = list(instr.values())[0]
            self.assertEqual(param, x1)
            self.assertEqual(value, expected[i])

        " Sweep dim = 2 with default apply = True, refresh = False "
        sw.reset()
        sw.sweep_linear(x1, 0, -1, dim=2)
        sx1 = sw.sweep_parameters[x1]
        self.assertEqual(sx1.parameter, x1)
        self.assertEqual(sx1.name, x1.name)
        self.assertEqual(sx1.dim, 2)
        sw.set_sweep_shape([3, 4, 5])
        npt.assert_equal(sx1.values, np.linspace(0, -1, 4))

        instrs = sw.get_ordered_instructions()
        expected = [[v] * 3 for v in np.linspace(0, -1, 4)] * 5
        expected = np.array(expected).flatten()
        bools = [True, False, False] * 4 * 5
        for i, instr in enumerate(instrs):
            if bools[i] is True:
                param = list(instr.keys())[0]
                value = list(instr.values())[0]
                self.assertEqual(param, x1)
                self.assertEqual(value, expected[i])
            else:
                self.assertEqual(instr, {})

        " Sweep dim = 2 with refresh = True "
        sw.reset()
        sw.sweep_linear(x1, 0, -1, dim=2, refresh=True)
        sx1 = sw.sweep_parameters[x1]
        self.assertEqual(sx1.parameter, x1)
        self.assertEqual(sx1.name, x1.name)
        self.assertEqual(sx1.dim, 2)
        sw.set_sweep_shape([3, 4, 5])
        npt.assert_equal(sx1.values, np.linspace(0, -1, 4))

        instrs = sw.get_ordered_instructions()
        expected = [[v] * 3 for v in np.linspace(0, -1, 4)] * 5
        expected = np.array(expected).flatten()
        for i, instr in enumerate(instrs):
            param = list(instr.keys())[0]
            value = list(instr.values())[0]
            self.assertEqual(param, x1)
            self.assertEqual(value, expected[i])

        " Sweep dim = 2 with apply = False "
        sw.reset()
        sw.sweep_linear(x1, 0, -1, dim=2, apply=False)
        sx1 = sw.sweep_parameters[x1]
        self.assertEqual(sx1.parameter, x1)
        self.assertEqual(sx1.name, x1.name)
        self.assertEqual(sx1.dim, 2)
        sw.set_sweep_shape([3, 4, 5])
        npt.assert_equal(sx1.values, np.linspace(0, -1, 4))

        instrs = sw.get_ordered_instructions()
        for i, instr in enumerate(instrs):
            self.assertEqual(instr, {})

    def test_reset(self):
        x1 = Parameter('x1', unit='V', set_cmd=None, get_cmd=None)
        sw = Sweeper('Sweeper')
        sw.sweep_linear(x1, 0, -1, dim=1)
        sw.set_sweep_shape([3, 4, 5])
        self.assertEqual(len(sw.sweep_parameters), 1)
        npt.assert_equal(sw.sweep_shape, np.array([3, 4, 5]))
        sw.clear_instructions()
        self.assertEqual(sw.sweep_parameters, {})
        npt.assert_equal(sw.sweep_shape, np.array([]))

    def test_set_config(self):
        x1 = Parameter('x1', unit='V', set_cmd=None, get_cmd=None)
        sw = Sweeper('Sweeper')

        npt.assert_equal(sw.sweep_shape, np.array([]))
        sw.set_config(sweep_shape=[1, 2, 3])
        npt.assert_equal(sw.sweep_shape, np.array([1, 2, 3]))

        self.assertEqual(sw.readouts, [])
        sw.set_config(readouts=[x1])
        self.assertEqual(sw.readouts[0], x1)

        m = Measurement(name='test')
        sw.set_config(measurement=m)
        self.assertEqual(sw.measurement, m)

        c = {x1: 1}
        self.assertEqual(sw.return_to, {})
        sw.set_config(return_to=c)
        self.assertEqual(sw.return_to[x1], 1)

        c = {x1: 1}
        self.assertEqual(sw.start_at, {})
        sw.set_config(start_at=c)
        self.assertEqual(sw.start_at[x1], 1)

        f = lambda d: d
        l = ['apply_method', 'readout_method']
        for m in l:
            sw.set_config(**{m: f})
            self.assertEqual(getattr(sw, m), f)

        l = [f'{i}_{j}_wait' for i in ['pre', 'post'] for j in ['process', 'readout']]
        for m in l:
            sw.set_config(**{m: 1})
            self.assertEqual(getattr(sw, m), 1)

        t = 'my note'
        self.assertEqual(sw.note, '')
        sw.set_config(note=t)
        self.assertEqual(sw.note, t)


if __name__ == '__main__':
    unittest.main()
