import unittest

from dstack.core import interpolation


class TestValidateInterpolation(unittest.TestCase):
    def test_empty_string(self):
        self.assertListEqual(interpolation.validate(""), [])

    def test_no_vars(self):
        self.assertListEqual(interpolation.validate("qwerty and 123 "), [])

    def test_escape_dollar(self):
        self.assertListEqual(interpolation.validate("do$$ar"), [])
        self.assertListEqual(interpolation.validate("dollar$$"), [])

    def test_brackets(self):
        self.assertListEqual(interpolation.validate("my ${VAR_NAME}"), ["VAR_NAME"])
        self.assertListEqual(interpolation.validate("my ${ NEW_VAR   }!"), ["NEW_VAR"])
        self.assertListEqual(interpolation.validate("my ${NEW_VAR}}}{}}{"), ["NEW_VAR"])

    def test_no_brackets(self):
        self.assertListEqual(interpolation.validate("$VAR_NAME4"), ["VAR_NAME4"])
        self.assertSetEqual(
            set(interpolation.validate("$VAR1-$VAR2$VAR3 $VAR4")), {"VAR1", "VAR2", "VAR3", "VAR4"}
        )

    def test_unescaped(self):
        self.assertRaises(ValueError, interpolation.validate, "It's a $")
        self.assertRaises(ValueError, interpolation.validate, "It's a $ dollar")
        self.assertRaises(ValueError, interpolation.validate, "It's a ${VAR")

    def test_illegal_characters(self):
        self.assertRaises(ValueError, interpolation.validate, "It's a ${V AR}")
        self.assertRaises(ValueError, interpolation.validate, "It's a ${V-A-R}")

    def test_missed(self):
        self.assertListEqual(interpolation.validate("$VAR_NAME", ["VAR_NAME"]), [])
        self.assertListEqual(interpolation.validate("$VAR_NAME and $VAR_NAME", ["VAR_NAME"]), [])
        self.assertListEqual(interpolation.validate("$VAR_NAME and $VAR_NAME", []), ["VAR_NAME"])
        self.assertListEqual(interpolation.validate("$VAR_NAME and $FOO", ["VAR_NAME"]), ["FOO"])
