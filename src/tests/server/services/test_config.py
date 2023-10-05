import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel
from dstack._internal.server.services.config import ServerConfigManager
from tests.server.common import create_backend, create_project, create_user, get_auth_headers


class TestServerConfigManager:
    class TestApplyConfig:
        @pytest.mark.asyncio
        async def test_creates_backend(self, test_db, session: AsyncSession, tmp_path: Path):
            await create_project(session=session, name="main")
            ServerConfigManager()
            config_filepath = tmp_path / "config.yaml"
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
                    }
                ]
            }
            with open(config_filepath, "w+") as f:
                yaml.dump(config, f)
            with patch("boto3.session.Session"), patch.object(
                settings, "SERVER_CONFIG_FILE_PATH", config_filepath
            ):
                manager = ServerConfigManager()
                await manager.apply_config(session)
            res = await session.execute(select(BackendModel))
            assert len(res.scalars().all()) == 1
