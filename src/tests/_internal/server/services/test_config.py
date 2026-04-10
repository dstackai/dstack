import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.aws.configurator import DEFAULT_REGIONS
from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.config import ServerConfigManager
from dstack._internal.server.testing.common import (
    create_backend,
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
                patch.object(settings, "SERVER_CONFIG_FILE_PATH", config_filepath),
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
                patch.object(settings, "SERVER_CONFIG_FILE_PATH", config_filepath),
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
                patch.object(settings, "SERVER_CONFIG_FILE_PATH", config_filepath),
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
                patch.object(settings, "SERVER_CONFIG_FILE_PATH", config_filepath),
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
                patch.object(settings, "SERVER_CONFIG_FILE_PATH", config_filepath),
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
