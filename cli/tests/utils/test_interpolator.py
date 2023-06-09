import unittest

from dstack._internal.utils.interpolator import VariablesInterpolator


def get_interpolator():
    return VariablesInterpolator({"run": {"args": "qwerty"}}, skip=["secrets"])


class TestVariablesInterpolator(unittest.TestCase):
    def test_empty(self):
        s = ""
        self.assertEqual(s, get_interpolator().interpolate(s))

    def test_bash(self):
        s = "${ENV}"
        self.assertEqual(s, get_interpolator().interpolate(s))

    def test_escaped_dollar(self):
        self.assertEqual("${{ENV}}", get_interpolator().interpolate("$${{ENV}}"))

    def test_escaped_dollar_middle(self):
        self.assertEqual("echo ${{ENV}}", get_interpolator().interpolate("echo $${{ENV}}"))

    def test_args(self):
        self.assertEqual("qwerty", get_interpolator().interpolate("${{ run.args }}"))

    def test_secrets(self):
        s = "${{ secrets.password  }}"
        self.assertEqual(s, get_interpolator().interpolate(s))

    def test_missing(self):
        s, missing = get_interpolator().interpolate("${{ env.name }}", return_missing=True)
        self.assertEqual("", s)
        self.assertListEqual(["env.name"], missing)

    def test_unclosed_pattern(self):
        with self.assertRaises(ValueError):
            get_interpolator().interpolate("${{ secrets.password }")

    def test_illegal_name(self):
        with self.assertRaises(ValueError):
            get_interpolator().interpolate("${{ secrets.pass-word }}")
        with self.assertRaises(ValueError):
            get_interpolator().interpolate("${{ .password }}")
        with self.assertRaises(ValueError):
            get_interpolator().interpolate("${{ password. }}")
        with self.assertRaises(ValueError):
            get_interpolator().interpolate("${{ secrets.password.hash }}")
        with self.assertRaises(ValueError):
            get_interpolator().interpolate("${{ secrets.007 }}")
