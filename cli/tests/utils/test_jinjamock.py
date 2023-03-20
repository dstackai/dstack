import unittest

import jinja2

from dstack.utils.jinjamock import JinjaMock


def get_template(s):
    return jinja2.Template(s, variable_start_string="${{")


class TestValidateJinjaMock(unittest.TestCase):
    def test_no_interpolation(self):
        text = "plaint text"
        template = get_template(text)
        self.assertEqual(text, template.render(secrets=JinjaMock("secrets")))

    def test_attribute(self):
        text = "password is ${{ secrets.password }}"
        template = get_template(text)
        self.assertEqual(text, template.render(secrets=JinjaMock("secrets")))

    def test_indexing(self):
        template = get_template("${{ secrets.password[1] }}")
        with self.assertRaises(ValueError):
            template.render(secrets=JinjaMock("secrets"))

    def test_chaining(self):
        template = get_template("${{ secrets.password.hash }}")
        with self.assertRaises(ValueError):
            template.render(secrets=JinjaMock("secrets"))

    def test_bad_pattern(self):
        with self.assertRaises(jinja2.exceptions.TemplateSyntaxError):
            get_template("${{ secrets.password }")
