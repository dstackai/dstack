import json
from pathlib import Path
from textwrap import dedent
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.aws.configurator import DEFAULT_REGIONS
from dstack._internal.core.backends.kubernetes.backend import KubernetesBackend
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesBackendConfigWithCreds,
    KubernetesConfig,
)
from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel, ImportModel, ProjectModel
from dstack._internal.server.services.config import (
    ServerConfigManager,
    config_yaml_to_backend_config,
    file_config_to_config,
)
from dstack._internal.server.testing.common import (
    create_backend,
    create_export,
    create_project,
    create_user,
)


class TestServerConfigManager:
    class TestApplyConfig:
        @pytest.mark.asyncio
        @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
        async def test_creates_backend(self, test_db, session: AsyncSession, tmp_path: Path):
            owner = await create_user(session=session, name="test_owner")
            await create_project(session=session, owner=owner, name="main")
            config_filepath = tmp_path / "config.yml"
            config = {
                "projects": [
                    {
                        "name": "main",
                        "backends": [
                            {
                                "type": "aws",
                                "creds": {
                                    "type": "access_key",
                                    "access_key": "1234",
                                    "secret_key": "1234",
                                },
                                "regions": ["us-west-1"],
                            }
                        ],
                    },
                    {
                        "name": "test",
                        "backends": [
                            {
                                "type": "aws",
                                "creds": {
                                    "type": "access_key",
                                    "access_key": "4321",
                                    "secret_key": "4321",
                                },
                                "regions": ["eu-west-1"],
                            }
                        ],
                    },
                ]
            }
            with open(config_filepath, "w+") as f:
                yaml.dump(config, f)
            with (
                patch("boto3.session.Session"),
                patch.object(settings, "SERVER_DIR_PATH", tmp_path),
                patch(
                    "dstack._internal.core.backends.aws.compute.get_vpc_id_subnets_ids_or_error"
                ),
            ):
                manager = ServerConfigManager()
                manager.load_config()
                await manager.apply_config(session, owner)
            p_res = await session.execute(select(ProjectModel))
            projects = p_res.scalars().all()
            assert len(projects) == 2
            b_res = await session.execute(select(BackendModel))
            backends = b_res.scalars().all()
            assert len(backends) == 2

        @pytest.mark.asyncio
        @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
        async def test_skips_update_when_source_config_matches(
            self, test_db, session: AsyncSession, tmp_path: Path
        ):
            owner = await create_user(session=session, name="test_owner")
            project = await create_project(session=session, owner=owner, name="main")
            creds = {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            }
            await create_backend(
                session=session,
                project_id=project.id,
                config={"regions": DEFAULT_REGIONS},
                auth=creds,
                source_config={"type": "aws", "regions": None},
                source_auth=creds,
            )
            config_filepath = tmp_path / "config.yml"
            config = {
                "projects": [{"name": "main", "backends": [{"type": "aws", "creds": creds}]}]
            }
            with open(config_filepath, "w+") as f:
                yaml.dump(config, f)
            with (
                patch.object(settings, "SERVER_DIR_PATH", tmp_path),
                patch(
                    "dstack._internal.server.services.backends.update_backend",
                    new_callable=AsyncMock,
                ) as update_backend,
            ):
                manager = ServerConfigManager()
                manager.load_config()
                await manager.apply_config(session, owner)
            update_backend.assert_not_called()

        @pytest.mark.asyncio
        @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
        async def test_populates_source_config_for_legacy_backend(
            self, test_db, session: AsyncSession, tmp_path: Path
        ):
            owner = await create_user(session=session, name="test_owner")
            project = await create_project(session=session, owner=owner, name="main")
            creds = {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            }
            backend = await create_backend(
                session=session,
                project_id=project.id,
                config={"regions": DEFAULT_REGIONS},
                auth=creds,
            )
            config_filepath = tmp_path / "config.yml"
            config = {
                "projects": [{"name": "main", "backends": [{"type": "aws", "creds": creds}]}]
            }
            with open(config_filepath, "w+") as f:
                yaml.dump(config, f)
            mock_session = Mock()
            mock_session.client.return_value = Mock()
            with (
                patch.object(settings, "SERVER_DIR_PATH", tmp_path),
                patch(
                    "dstack._internal.core.backends.aws.auth.authenticate",
                    return_value=mock_session,
                ),
                patch(
                    "dstack._internal.core.backends.aws.compute.get_vpc_id_subnets_ids_or_error"
                ),
            ):
                manager = ServerConfigManager()
                manager.load_config()
                await manager.apply_config(session, owner)
            await session.refresh(backend)
            assert backend.source_config is not None
            assert backend.source_auth is not None
            assert json.loads(backend.source_config)["regions"] is None
            assert json.loads(backend.source_auth.get_plaintext_or_error()) == creds
            with (
                patch.object(settings, "SERVER_DIR_PATH", tmp_path),
                patch(
                    "dstack._internal.server.services.backends.update_backend",
                    new_callable=AsyncMock,
                ) as update_backend,
            ):
                manager = ServerConfigManager()
                manager.load_config()
                await manager.apply_config(session, owner)
            update_backend.assert_not_called()

        @pytest.mark.asyncio
        @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
        async def test_forces_update_when_current_backend_config_is_unavailable(
            self, test_db, session: AsyncSession, tmp_path: Path
        ):
            owner = await create_user(session=session, name="test_owner")
            project = await create_project(session=session, owner=owner, name="main")
            creds = {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            }
            await create_backend(
                session=session,
                project_id=project.id,
                config={"regions": DEFAULT_REGIONS},
                auth=creds,
                source_config={"type": "aws", "regions": None},
                source_auth=creds,
            )
            config_filepath = tmp_path / "config.yml"
            config = {
                "projects": [{"name": "main", "backends": [{"type": "aws", "creds": creds}]}]
            }
            with open(config_filepath, "w+") as f:
                yaml.dump(config, f)
            with (
                patch.object(settings, "SERVER_DIR_PATH", tmp_path),
                patch(
                    "dstack._internal.server.services.backends.get_backend_config",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "dstack._internal.server.services.backends.update_backend",
                    new_callable=AsyncMock,
                ) as update_backend,
            ):
                manager = ServerConfigManager()
                manager.load_config()
                await manager.apply_config(session, owner)
            update_backend.assert_awaited_once()

        @pytest.mark.asyncio
        @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
        async def test_new_project_imports_global_exports(
            self, test_db, session: AsyncSession, tmp_path: Path
        ):
            owner = await create_user(session=session, name="test_owner")
            exporter_project = await create_project(session=session, owner=owner, name="exporter")
            await create_export(
                session=session,
                exporter_project=exporter_project,
                importer_projects=[],
                exported_fleets=[],
                name="global-export",
                is_global=True,
            )
            config_filepath = tmp_path / "config.yml"
            config = {"projects": [{"name": "new-project"}]}
            with open(config_filepath, "w+") as f:
                yaml.dump(config, f)
            with patch.object(settings, "SERVER_DIR_PATH", tmp_path):
                manager = ServerConfigManager()
                manager.load_config()
                await manager.apply_config(session, owner)
            new_project_res = await session.execute(
                select(ProjectModel).where(ProjectModel.name == "new-project")
            )
            new_project = new_project_res.scalar_one()
            imports_res = await session.execute(
                select(ImportModel).where(ImportModel.project_id == new_project.id)
            )
            imports = imports_res.scalars().all()
            assert len(imports) == 1


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

        with patch.object(settings, "SERVER_DIR_PATH", tmp_path):
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

        with patch.object(settings, "SERVER_DIR_PATH", tmp_path):
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

        with patch.object(settings, "SERVER_DIR_PATH", tmp_path):
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
        assert isinstance(backend_config, KubernetesBackendConfigWithCreds)
        # `KubernetesConfig` adds no fields to the parsed config
        backend = KubernetesBackend(cast(KubernetesConfig, backend_config))

        cluster = backend.compute().region_cluster_map[""]
        assert cluster.api_client.configuration.host == (  # pyright: ignore[reportAttributeAccessIssue]
            "https://gpu-cluster.internal.example.com:6443"
        )
        assert cluster.proxy_jump.hostname == "204.12.171.137"
        assert cluster.proxy_jump.port == 32000

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
        assert isinstance(backend_config, KubernetesBackendConfigWithCreds)
        # `KubernetesConfig` adds no fields to the parsed config
        backend = KubernetesBackend(cast(KubernetesConfig, backend_config))

        cluster = backend.compute().region_cluster_map[""]
        assert cluster.namespace == "default"
