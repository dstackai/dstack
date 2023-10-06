import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.azure import AzureConfigInfoWithCreds, AzureDefaultCreds
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel
from dstack._internal.server.services.config import ServerConfigManager
from tests._internal.server.common import (
    create_backend,
    create_project,
    create_user,
    get_auth_headers,
)


class TestServerConfigManager:
    class TestInitConfig:
        @pytest.mark.asyncio
        async def test_inits_backend(self, test_db, session: AsyncSession, tmp_path: Path):
            await create_project(session=session, name="main")
            config_filepath = tmp_path / "config.yaml"
            with patch.object(settings, "SERVER_CONFIG_FILE_PATH", config_filepath), patch(
                "dstack._internal.server.services.backends.list_available_backend_types"
            ) as list_available_backend_types_mock, patch(
                "dstack._internal.server.services.backends.get_configurator"
            ) as get_configurator_mock, patch(
                "dstack._internal.server.services.backends.create_backend"
            ) as create_backend_mock:
                list_available_backend_types_mock.return_value = [BackendType.AZURE]
                default_config = AzureConfigInfoWithCreds(
                    tenant_id="test_tenant",
                    subscription_id="test_subscription",
                    locations=["westeurope"],
                    creds=AzureDefaultCreds(),
                )
                get_configurator_mock.return_value.get_default_configs.return_value = [
                    default_config
                ]
                manager = ServerConfigManager()
                await manager.init_config(session)
                list_available_backend_types_mock.assert_called()
                get_configurator_mock.assert_called()
                create_backend_mock.assert_called()
                assert manager.config.projects[0].backends[0] == default_config

    class TestApplyConfig:
        @pytest.mark.asyncio
        async def test_creates_backend(self, test_db, session: AsyncSession, tmp_path: Path):
            await create_project(session=session, name="main")
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
                manager.load_config()
                await manager.apply_config(session)
            res = await session.execute(select(BackendModel))
            assert len(res.scalars().all()) == 1
