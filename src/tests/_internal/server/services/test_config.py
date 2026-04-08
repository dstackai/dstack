from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.config import ServerConfigManager
from dstack._internal.server.testing.common import (
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
