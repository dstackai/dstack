import unittest

from dstack._internal.configurators import HomeDirUnsetError, validate_local_path


class TestLocalPath(unittest.TestCase):
    def test_absolute(self):
        path = "/root/.cache"
        self.assertEqual(path, validate_local_path(path, None, "."))

    def test_relative(self):
        path = ".cache/pip"
        self.assertEqual("/workflow/" + path, validate_local_path(path, None, "."))

    def test_relative_dot(self):
        self.assertEqual("/workflow/cache/pip", validate_local_path("./cache/pip", None, "."))

    def test_relative_dot_twice(self):
        self.assertEqual("/workflow/cache/pip", validate_local_path("././cache/pip", None, "."))

    def test_home(self):
        home = "/root"
        self.assertEqual(home, validate_local_path("~", home, "."))

    def test_startswith_home(self):
        self.assertEqual("/root/.cache", validate_local_path("~/.cache", "/root", "."))

    def test_missing_home(self):
        with self.assertRaises(HomeDirUnsetError):
            validate_local_path("~/.cache", None, ".")
