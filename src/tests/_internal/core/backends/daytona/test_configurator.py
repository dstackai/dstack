import json
from unittest.mock import patch

import pytest

from dstack._internal.core.backends.configurators import get_configurator
from dstack._internal.core.backends.daytona.configurator import DaytonaConfigurator
from dstack._internal.core.backends.daytona.models import (
    DaytonaBackendConfigWithCreds,
    DaytonaCreds,
)
from dstack._internal.core.errors import (
    BackendInvalidCredentialsError,
    ServerClientError,
)
from dstack._internal.core.models.backends.base import BackendType


@pytest.fixture
def client():
    with patch(
        "dstack._internal.core.backends.daytona.configurator.DaytonaAPIClient", autospec=True
    ) as client_class:
        client = client_class.return_value
        client.get_current_api_key.return_value = {"organizationId": "test-org"}
        client.get_shared_regions.return_value = [{"id": "us"}, {"id": "eu"}, {"id": "ap"}]
        yield client


class TestDaytonaConfigurator:
    def test_registered(self):
        assert isinstance(get_configurator(BackendType.DAYTONA), DaytonaConfigurator)

    def test_validate_config_without_region_restrictions(self, client):
        config = DaytonaBackendConfigWithCreds(creds=DaytonaCreds(api_key="test-key"))

        DaytonaConfigurator().validate_config(config, default_creds_enabled=False)

        client.get_current_api_key.assert_called_once_with()
        client.get_shared_regions.assert_not_called()

    def test_validate_config_accepts_gpu_and_discovered_cpu_regions(self, client):
        config = DaytonaBackendConfigWithCreds(
            creds=DaytonaCreds(api_key="test-key"), regions=["earth", "eu", "ap"]
        )

        DaytonaConfigurator().validate_config(config, default_creds_enabled=False)

        client.get_current_api_key.assert_called_once_with()
        client.get_shared_regions.assert_called_once_with()

    def test_validate_config_rejects_unknown_regions(self, client):
        config = DaytonaBackendConfigWithCreds(
            creds=DaytonaCreds(api_key="test-key"), regions=["unknown"]
        )

        with pytest.raises(ServerClientError) as exc_info:
            DaytonaConfigurator().validate_config(config, default_creds_enabled=False)

        assert exc_info.value.fields == [["regions"]]
        assert "unknown" in exc_info.value.msg

    def test_validate_config_preserves_authentication_error(self, client):
        config = DaytonaBackendConfigWithCreds(
            creds=DaytonaCreds(api_key="invalid"), regions=["earth"]
        )
        error = BackendInvalidCredentialsError(fields=[["creds", "api_key"]])
        client.get_current_api_key.side_effect = error

        with pytest.raises(BackendInvalidCredentialsError) as exc_info:
            DaytonaConfigurator().validate_config(config, default_creds_enabled=False)

        assert exc_info.value is error
        client.get_shared_regions.assert_not_called()

    def test_stored_config_keeps_credentials_separate(self):
        config = DaytonaBackendConfigWithCreds(
            creds=DaytonaCreds(api_key="test-secret"), regions=["earth", "us"]
        )
        configurator = DaytonaConfigurator()

        record = configurator.create_backend(project_name="main", config=config)

        assert json.loads(record.config) == {"type": "daytona", "regions": ["earth", "us"]}
        assert json.loads(record.auth) == {"type": "api_key", "api_key": "test-secret"}
        assert configurator.get_backend_config_with_creds(record) == config
        public_config = configurator.get_backend_config_without_creds(record).model_dump()
        assert public_config == json.loads(record.config)
        assert "test-secret" not in json.dumps(public_config)
