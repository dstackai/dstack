import json
import sys
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pytest
import yaml

from dstack._internal.core.backends.kubernetes.backend import KubernetesBackend
from dstack._internal.server import settings
from dstack._internal.server.services.config import (
    ServerConfigManager,
    config_yaml_to_backend_config,
    file_config_to_config,
)


class TestCrusoeBackendConfig:
    def test_config_parsing(self, tmp_path: Path):
        config_yaml_path = tmp_path / "config.yml"
        config_dict = {
            "projects": [
                {
                    "name": "main",
                    "backends": [
                        {
                            "type": "crusoe",
                            "project_id": "test-project-id",
                            "regions": ["us-east1-a"],
                            "creds": {
                                "type": "access_key",
                                "access_key": "test-access-key",
                                "secret_key": "test-secret-key",
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

        assert backend_cfg.type == "crusoe"
        assert backend_cfg.project_id == "test-project-id"
        assert backend_cfg.regions == ["us-east1-a"]
        assert backend_cfg.creds.access_key == "test-access-key"
        assert backend_cfg.creds.secret_key == "test-secret-key"


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


class TestKubernetesBackendConfig:
    def test_ui_config_embedded_kubeconfig_initializes_backend(self):
        config_yaml = dedent(
            """
            type: kubernetes
            kubeconfig:
              data: |
                apiVersion: v1
                kind: Config
                current-context: gpu-training

                clusters:
                - name: gpu-training
                  cluster:
                    server: https://gpu-cluster.internal.example.com:6443
                    insecure-skip-tls-verify: true

                users:
                - name: ml-engineer
                  user:
                    token: test-token

                contexts:
                - name: gpu-training
                  context:
                    cluster: gpu-training
                    user: ml-engineer

            proxy_jump:
              hostname: 204.12.171.137
              port: 32000
            """
        )

        backend_config = config_yaml_to_backend_config(config_yaml)
        backend = KubernetesBackend(backend_config)

        assert backend.compute().api.api_client.configuration.host == (
            "https://gpu-cluster.internal.example.com:6443"
        )
        assert backend.compute().proxy_jump.hostname == "204.12.171.137"
        assert backend.compute().proxy_jump.port == 32000

    def test_kubeconfig_context_namespace_does_not_set_backend_namespace(self):
        config_yaml = dedent(
            """
            type: kubernetes
            kubeconfig:
              data: |
                apiVersion: v1
                kind: Config
                current-context: gpu-training

                clusters:
                - name: gpu-training
                  cluster:
                    server: https://gpu-cluster.internal.example.com:6443
                    insecure-skip-tls-verify: true

                users:
                - name: ml-engineer
                  user:
                    token: test-token

                contexts:
                - name: gpu-training
                  context:
                    cluster: gpu-training
                    user: ml-engineer
                    namespace: training-jobs

            proxy_jump:
              hostname: 204.12.171.137
              port: 32000
            """
        )

        backend_config = config_yaml_to_backend_config(config_yaml)
        backend = KubernetesBackend(backend_config)

        assert backend.compute().config.namespace == "default"
