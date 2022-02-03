import unittest

import qube.utils.path
import os


class TestPaths(unittest.TestCase):
    def test_get_folder(self):
        self.assertEqual(qube.utils.path.get_folder('test.txt'), '')
        self.assertEqual(qube.utils.path.get_folder('test.'), '')
        self.assertEqual(qube.utils.path.get_folder('test'), 'test')
        path = os.path.join('test', 'other')
        self.assertEqual(qube.utils.path.get_folder(path), path)
        path = os.path.join('test', 'other', 'file.txt')
        self.assertEqual(qube.utils.path.get_folder(path), os.path.join('test', 'other'))

    def test_get_filename(self):
        self.assertEqual(qube.utils.path.get_filename('test.txt', ext=True), 'test.txt')
        self.assertEqual(qube.utils.path.get_filename('test.txt', ext=False), 'test')
        self.assertEqual(qube.utils.path.get_filename('test.', ext=True), 'test.')
        self.assertEqual(qube.utils.path.get_filename('test.', ext=False), 'test')
        self.assertRaises(ValueError, qube.utils.path.get_filename, 'test', True)
        self.assertRaises(ValueError, qube.utils.path.get_filename, 'test', False)
        path = os.path.join('test', 'other')
        self.assertRaises(ValueError, qube.utils.path.get_filename, path, True)
        self.assertRaises(ValueError, qube.utils.path.get_filename, path, False)
        path = os.path.join('test', 'other', 'file.txt')
        self.assertEqual(qube.utils.path.get_filename(path, ext=True), 'file.txt')
        self.assertEqual(qube.utils.path.get_filename(path, ext=False), 'file')

    def test_get_file_extension(self):
        self.assertEqual(qube.utils.path.get_file_extension('test.txt'), '.txt')
        self.assertEqual(qube.utils.path.get_file_extension('test.'), '.')
        self.assertRaises(ValueError, qube.utils.path.get_file_extension, 'test')
        path = os.path.join('test', 'other')
        self.assertRaises(ValueError, qube.utils.path.get_file_extension, path)
        path = os.path.join('test', 'other', 'file.txt')
        self.assertEqual(qube.utils.path.get_file_extension(path), '.txt')


if __name__ == '__main__':
    unittest.main()
