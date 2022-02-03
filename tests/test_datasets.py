import unittest

import numpy as np
import numpy.testing as npt

from qube.postprocess import dataset


class TestData(unittest.TestCase):
    dataset_class = dataset.Data

    def test_defaults(self):
        ds = self.dataset_class(name='test', value=2)
        self.assertEqual(ds.name, 'test')
        self.assertEqual(ds.value, 2)
        self.assertEqual(ds.unit, dataset.default_unit)
        self.assertEqual(ds.metadata, {})

    def test_unit(self):
        input_expected = [
            ['us', 'us'],
            ['', dataset.default_unit],
            [None, dataset.default_unit],
            [2, str(2)],
        ]

        for case in input_expected:
            input_unit, expected = case
            ds = dataset.Data(name='test', value=2, unit=input_unit)
            self.assertEqual(ds.unit, expected)

    def test_value(self):
        cases = [2, [1, 2], 'value']
        for value in cases:
            ds = dataset.Data(name='test', value=value)
            self.assertEqual(ds.value, value)
        ds = dataset.Data(name='test', value=np.array([1, 2]))
        npt.assert_equal(ds.value, np.array([1, 2]))

    def test_copy(self):
        ds = self.dataset_class(name='test', value=2)
        ds_copy = ds.copy()
        self.assertTrue(id(ds) != id(ds_copy))
        self.assertEqual(ds.name, ds_copy.name)
        self.assertEqual(ds.unit, ds_copy.unit)
        self.assertEqual(ds.value, ds_copy.value)
        self.assertEqual(ds.metadata, ds_copy.metadata)


class TestDataset(TestData):
    dataset_class = dataset.Dataset

    def test_axes(self):
        ds = self.dataset_class(name='test', value=2)
        self.assertEqual(ds.axes, list())
        ds = self.dataset_class(name='test', value=np.zeros((10, 4)))
        self.assertEqual(len(ds.counter_axes), 2)
        self.assertEqual(len(ds.axes), 2)
        self.assertEqual(len(ds.axes[0].value), 10)
        self.assertEqual(len(ds.axes[1].value), 4)
        npt.assert_equal(ds.axes[0].value, np.arange(10, dtype=int))
        npt.assert_equal(ds.axes[1].value, np.arange(4, dtype=int))
        self.assertEqual(ds.axes[0].dim, 0)
        self.assertEqual(ds.axes[1].dim, 1)

    def test_value(self):
        cases = [2, [1, 2], 'value']
        for value in cases:
            ds = dataset.Dataset(name='test', value=value)
            npt.assert_equal(ds.value, np.array(value))

    def test_validate_axes(self):
        ds = self.dataset_class(name='test', value=np.zeros((10, 4)))
        values = [np.arange(10), np.arange(4), np.arange(5)]
        dims = [0, 1, 2]
        expected = [
            [True, False, False],
            [False, True, False],
            [False, False, False],
        ]
        for i, vi in enumerate(values):
            for j, di in enumerate(dims):
                s = dataset.Axis('test', value=vi, dim=di)
                self.assertEqual(ds.is_valid_axis(s), expected[i][j])

    def test_add_axis(self):
        ds = self.dataset_class(name='test', value=np.zeros((10, 4)), axes={})
        s = dataset.Axis('test', value=np.arange(10), dim=0, )
        ds.add_axis(axis=s)
        self.assertRaises(ValueError, ds.add_axis, 'random_axis')

    def test_ndim(self):
        value_ndim = [
            [[10], 1],
            [[10, 4], 2],
        ]
        for v in value_ndim:
            value, ndim = v
            ds = self.dataset_class(name='test', value=np.zeros(value))
            self.assertEqual(ds.ndim, ndim)


class TestStatic(TestData):
    dataset_class = dataset.Static


class TestAxis(unittest.TestCase):
    dataset_class = dataset.Axis

    def test_defaults(self):
        ds = self.dataset_class(name='test', value=2, dim=1)
        self.assertEqual(ds.name, 'test')
        self.assertEqual(ds.value, 2)
        self.assertEqual(ds.unit, dataset.default_unit)
        self.assertEqual(ds.metadata, {})
        self.assertEqual(ds.dim, 1)
        self.assertEqual(ds.offset, None)

    def test_valid_dim(self):
        valid_values = [0, 1, 2, None]
        for dim in valid_values:
            ds = dataset.Axis(name='test', value=2, dim=dim)
            self.assertEqual(ds.dim, dim)

    def test_not_valid_dim(self):
        not_valid_values = [-1, 'a', 0.0]
        for dim in not_valid_values:
            self.assertRaises(ValueError, dataset.Axis, 'test', 2, dim)

    def test_offset(self):
        valid_values = [0, 1.1, -2.3]
        for offset in valid_values:
            ds = dataset.Axis(name='test', value=2, offset=offset)
            self.assertEqual(ds.offset, offset)
            # npt.assert_equal(np.asarray(ds.value, dtype=float), np.asarray(np.array(2) + offset, dtype=float))

    def test_value(self):
        cases = [2, [1, 2], 'value']
        for value in cases:
            ds = dataset.Axis(name='test', value=value)
            npt.assert_equal(ds.value, np.array(value))


class TestSequenceSlot(unittest.TestCase):
    dataset_class = dataset.SequenceSlot

    def test_defaults(self):
        ds = self.dataset_class(name='test', value=2, index=1)
        self.assertEqual(ds.name, 'test')
        self.assertEqual(ds.value, 2)
        self.assertEqual(ds.unit, dataset.default_unit)
        self.assertEqual(ds.metadata, {})
        self.assertEqual(ds.index, 1)

    def test_index(self):
        ds = self.dataset_class(name='test', value=2, index=1)
        self.assertEqual(ds.index, 1)
        self.assertRaises(ValueError, self.dataset_class, 'test', 2, 1.1)
        self.assertRaises(ValueError, self.dataset_class, 'test', 2, '1')


class TestSequence(unittest.TestCase):
    dataset_class = dataset.Sequence

    def test_defaults(self):
        ds = self.dataset_class(name='test', slots={})
        self.assertEqual(ds.name, 'test')
        self.assertEqual(ds.value, {})
        self.assertEqual(ds.value, ds.slots)
        self.assertEqual(ds.unit, dataset.default_unit)
        self.assertEqual(ds.metadata, {})

    def test_get(self):
        slots = {}
        slots[0] = dataset.SequenceSlot('test1', 1, 0)
        slots[1] = dataset.SequenceSlot('test2', 2, 1)
        ds = self.dataset_class(name='test', slots=slots)
        self.assertEqual(ds.get_instructions(), ['test1', 'test2'])
        self.assertEqual(ds.get_values(), [1, 2])


if __name__ == '__main__':
    unittest.main()
