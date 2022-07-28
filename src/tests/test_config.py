import tempfile
from pathlib import Path
from typing import Dict
from unittest import TestCase

from yaml import dump

from dstack.server import __server_url__
from dstack.config import from_yaml_file, Profile


class TestYamlConfig(TestCase):
    def setUp(self):
        self.config_path = Path(tempfile.gettempdir()) / "config.yaml"
        parent = self.config_path.parent
        if parent and not parent.exists():
            parent.mkdir(parents=True)

    def tearDown(self):
        if self.config_path.exists():
            self.config_path.unlink()

    def test_empty_config(self):
        conf = from_yaml_file(self.config_path)
        # shouldn't raise an exception
        conf.list_profiles()
        conf.add_or_replace_profile(Profile("default", "test_token", __server_url__, verify=True))
        conf.save()
        conf = from_yaml_file(self.config_path)
        self.assertEqual(1, len(conf.list_profiles()))
        self.assertEqual("test_token", conf.get_profile("default").token)

    def test_save_and_load(self):
        self.create_yaml_file(self.config_path, self.conf_example())
        conf = from_yaml_file(self.config_path)
        default = conf.get_profile("default")
        profile = conf.get_profile("other")
        profile.token = "my_new_token"
        conf.add_or_replace_profile(profile)
        conf.save()
        conf = from_yaml_file(self.config_path)
        self.assertEqual(profile.token, conf.get_profile("other").token)
        self.assertEqual(default.token, conf.get_profile("default").token)

    @staticmethod
    def conf_example() -> Dict:
        return {"profiles": {"default": {"token": "token1"},
                             "other": {"token": "token2"}}}

    @staticmethod
    def create_yaml_file(path: Path, content: Dict):
        content = dump(content)
        path.write_text(content, encoding="utf-8")

    def test_set_get_properties(self):
        conf = from_yaml_file(self.config_path)
        conf.set_property("simple", "my value")
        self.assertEqual("my value", conf.get_property("simple"))
        self.assertIsNone(conf.get_property("missing"))
        conf.set_property("a.b", "hello")
        conf.set_property("a.c", "world")

        self.assertEqual("hello", conf.get_property("a.b"))
        self.assertEqual("world", conf.get_property("a.c"))

        conf.set_property("a.x.c", "hello")
        conf.set_property("a.y.d", "world")

        self.assertEqual("hello", conf.get_property("a.x.c"))
        self.assertEqual("world", conf.get_property("a.y.d"))

    def test_get_float_property_saved_by_java_library(self):
        content = self.conf_example()
        content.update({"server": {"version": 0.1}})
        self.create_yaml_file(self.config_path, content)

        conf = from_yaml_file(self.config_path)
        self.assertEqual("0.1", conf.get_property("server.version"))

