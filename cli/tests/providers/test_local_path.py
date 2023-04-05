import unittest

from dstack.providers import Provider


def make_provider(**kwargs):
    p = Provider("test")
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


class TestLocalPath(unittest.TestCase):
    def test_absolute(self):
        p = make_provider()
        path = "/root/.cache"
        self.assertEqual(path, p._validate_local_path(path))

    def test_relative(self):
        p = make_provider()
        path = ".cache/pip"
        self.assertEqual(path, p._validate_local_path(path))

    def test_relative_dot(self):
        p = make_provider()
        self.assertEqual("cache/pip", p._validate_local_path("./cache/pip"))

    def test_relative_dot_twice(self):
        p = make_provider()
        self.assertEqual("cache/pip", p._validate_local_path("././cache/pip"))

    def test_home(self):
        home = "/root"
        p = make_provider(home_dir=home)
        self.assertEqual(home, p._validate_local_path("~"))

    def test_startswith_home(self):
        p = make_provider(home_dir="/root")
        self.assertEqual("/root/.cache", p._validate_local_path("~/.cache"))

    def test_missing_home(self):
        p = make_provider()
        with self.assertRaises(KeyError):
            p._validate_local_path("~/.cache")
