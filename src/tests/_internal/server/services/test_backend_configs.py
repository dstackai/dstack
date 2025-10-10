import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from dstack._internal.server import settings
from dstack._internal.server.services.config import (
    ServerConfigManager,
    file_config_to_config,
)


@pytest.mark.skipif(sys.version_info < (3, 10), reason="Nebius requires Python 3.10")
class TestNebiusBackendConfig:
    def test_with_filename(self, tmp_path: Path):
        creds_json = {
            "subject-credentials": {
                "type": "JWT",
                "alg": "RS256",
                "private-key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
                "kid": "publickey-e00test",
                "iss": "serviceaccount-e00test",
                "sub": "serviceaccount-e00test",
            }
        }
        creds_file = tmp_path / "nebius_creds.json"
        creds_file.write_text(json.dumps(creds_json))

        config_yaml_path = tmp_path / "config.yml"
        config_dict = {
            "projects": [
                {
                    "name": "main",
                    "backends": [
                        {
                            "type": "nebius",
                            "creds": {"type": "service_account", "filename": str(creds_file)},
                        }
                    ],
                }
            ]
        }
        config_yaml_path.write_text(yaml.dump(config_dict))

        with patch.object(settings, "SERVER_CONFIG_FILE_PATH", config_yaml_path):
            m = ServerConfigManager()
            assert m.load_config()
            assert m.config is not None
            assert m.config.projects is not None
            assert len(m.config.projects) > 0
            assert m.config.projects[0].backends is not None
            backend_file_cfg = m.config.projects[0].backends[0]
            backend_cfg = file_config_to_config(backend_file_cfg)

        assert backend_cfg.type == "nebius"
        assert backend_cfg.creds.service_account_id == "serviceaccount-e00test"
        assert backend_cfg.creds.public_key_id == "publickey-e00test"
        assert (
            backend_cfg.creds.private_key_content
            == "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n"
        )

    def test_with_private_key_file(self, tmp_path: Path):
        pk_file = tmp_path / "private.key"
        pk_file.write_text("TEST_PRIVATE_KEY")

        config_yaml_path = tmp_path / "config.yml"
        config_dict = {
            "projects": [
                {
                    "name": "main",
                    "backends": [
                        {
                            "type": "nebius",
                            "projects": ["project-e00test"],
                            "creds": {
                                "type": "service_account",
                                "service_account_id": "serviceaccount-e00test",
                                "public_key_id": "publickey-e00test",
                                "private_key_file": str(pk_file),
                            },
                        }
                    ],
                }
            ]
        }
        config_yaml_path.write_text(yaml.dump(config_dict))

        with patch.object(settings, "SERVER_CONFIG_FILE_PATH", config_yaml_path):
            m = ServerConfigManager()
            assert m.load_config()
            assert m.config is not None
            assert m.config.projects is not None
            assert len(m.config.projects) > 0
            assert m.config.projects[0].backends is not None
            backend_file_cfg = m.config.projects[0].backends[0]
            backend_cfg = file_config_to_config(backend_file_cfg)

        assert backend_cfg.type == "nebius"
        assert backend_cfg.creds.service_account_id == "serviceaccount-e00test"
        assert backend_cfg.creds.public_key_id == "publickey-e00test"
        assert backend_cfg.creds.private_key_content == "TEST_PRIVATE_KEY"
