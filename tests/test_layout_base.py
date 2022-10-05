import unittest

from qube.layout.base import format_dict, try_fmts, ConfigBase, fmt_func


class TestMisc(unittest.TestCase):
    def test_fmt_func(self):
        self.assertEqual(fmt_func(str), str)
        self.assertEqual(fmt_func(int), int)
        self.assertEqual(fmt_func(None)(1), 1)
        self.assertEqual(fmt_func([int, str])(1.0), try_fmts(int, str)(1.0))
        self.assertEqual(fmt_func([int, str])('1.1'), try_fmts(int, str)('1.1'))


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        c = ConfigBase()
        self.assertEqual(c.fullpath, None)
        self.assertEqual(c.sections, [])

    def test_format_dict(self):
        d = {
            1: '2',
            '2': '3',
            't1': '1',
            't2': '1,',
            't3': '1, 2,3',
            't4': '0.6',
        }
        key_fmt = str
        value_fmt = str
        value_sep = None
        expected = {
            '1': '2',
            '2': '3',
            't1': '1',
            't2': '1,',
            't3': '1, 2,3',
            't4': '0.6',
        }
        self.assertEqual(format_dict(d, key_fmt, value_fmt, value_sep), expected)

        key_fmt = str
        value_fmt = str
        value_sep = ','
        expected = {
            '1': ['2'],
            '2': ['3'],
            't1': ['1'],
            't2': ['1'],
            't3': ['1', '2', '3'],
            't4': ['0.6'],
        }
        self.assertEqual(format_dict(d, key_fmt, value_fmt, value_sep), expected)

        # Error trying to convert to int
        self.assertRaises(ValueError, format_dict, d, str, int, None)

        d = {
            'facecolor': 'red',
            'alpha': '0.8',
        }
        key_fmt = str
        value_fmt = try_fmts(float, str)
        value_sep = None
        expected = {
            'facecolor': 'red',
            'alpha': 0.8,
        }
        self.assertEqual(format_dict(d, key_fmt, value_fmt, value_sep), expected)


if __name__ == '__main__':
    unittest.main()
