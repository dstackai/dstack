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

    def test_no_config(self):
        with self.assertRaises(ConfigError):
            config = load_config(self.config_path)

    def test_full_config(self):
        self.config_path.write_text(dump({
            "backend": "aws",
            "bucket": "test-bucket-2",
            "region": "test-region-2",
            "profile": "test-profile-2"
        }), encoding="utf-8")
        config = load_config(self.config_path)
        self.assertTrue(isinstance(config.backend_config, AwsBackendConfig))
        self.assertEqual("test-bucket-2", config.backend_config.bucket_name)
        self.assertEqual("test-region-2", config.backend_config.region_name)
        self.assertEqual("test-profile-2", config.backend_config.profile_name)

    def test_basic_config(self):
        self.config_path.write_text(dump({
            "backend": "aws",
            "bucket": "test-bucket-3",
        }), encoding="utf-8")
        config = load_config(self.config_path)
        self.assertTrue(isinstance(config.backend_config, AwsBackendConfig))
        self.assertEqual("test-bucket-3", config.backend_config.bucket_name)
        self.assertIsNone(config.backend_config.region_name)
        self.assertIsNone(config.backend_config.profile_name)


class TestEnvConfig(TestCase):
    def setUp(self):
        self.config_path = Path(tempfile.gettempdir()) / "config.yaml"

    def tearDown(self):
        if "DSTACK_AWS_S3_BUCKET" in os.environ:
            del os.environ["DSTACK_AWS_S3_BUCKET"]
        if "DSTACK_AWS_S3_REGION" in os.environ:
            del os.environ["DSTACK_AWS_S3_REGION"]

    def test_no_env(self):
        with self.assertRaises(ConfigError):
            config = load_config(self.config_path)
            print(config)

    def test_env(self):
        os.environ["DSTACK_AWS_S3_BUCKET"] = "test-bucket-4"
        os.environ["DSTACK_AWS_REGION"] = "test-region-4"
        config = load_config(self.config_path)
        self.assertTrue(isinstance(config.backend_config, AwsBackendConfig))
        self.assertEqual("test-bucket-4", config.backend_config.bucket_name)
        self.assertEqual("test-region-4", config.backend_config.region_name)
