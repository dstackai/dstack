import tempfile
from unittest import TestCase

from yaml import dump

from dstack.config import *


class TestConfig(TestCase):
    def setUp(self):
        self.config_path = Path(tempfile.gettempdir()) / "config.yaml"
        parent = self.config_path.parent
        if parent and not parent.exists():
            parent.mkdir(parents=True)

    def tearDown(self):
        if self.config_path.exists():
            self.config_path.unlink()

    def test_config_1(self):
        with self.assertRaises(ConfigError):
            config = load_config(self.config_path)

    def test_config_2(self):
        self.config_path.write_text(dump({
            "backend": "aws",
            "bucket": "test-bucket",
        }), encoding="utf-8")
        config = load_config(self.config_path)
        self.assertTrue(isinstance(config.backend_config, AwsBackendConfig))
        self.assertEqual("test-bucket", config.backend_config.bucket_name)
