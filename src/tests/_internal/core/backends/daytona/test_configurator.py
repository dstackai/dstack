import json
from unittest.mock import patch

import pytest

from dstack._internal.core.backends.daytona.api_client import API_URL
from dstack._internal.core.backends.daytona.configurator import DaytonaConfigurator
from dstack._internal.core.backends.daytona.models import (
    DaytonaBackendConfigWithCreds,
    DaytonaCreds,
)
from dstack._internal.core.errors import (
    BackendInvalidCredentialsError,
    ServerClientError,
)


@pytest.fixture
def client():
    with patch(
        "dstack._internal.core.backends.daytona.configurator.DaytonaAPIClient", autospec=True
    ) as client_class:
        client = client_class.return_value
        client.get_current_api_key.return_value = {
            "organizationId": "test-org",
            "permissions": ["write:sandboxes", "delete:sandboxes", "read:limits"],
        }
        client.get_shared_regions.return_value = [{"id": "us"}, {"id": "eu"}, {"id": "ap"}]
        yield client


class TestDaytonaConfigurator:
    def test_validate_config_accepts_only_required_permissions(self, client):
        config = DaytonaBackendConfigWithCreds(creds=DaytonaCreds(api_key="test-key"))

        DaytonaConfigurator().validate_config(config, default_creds_enabled=False)

        client.get_current_api_key.assert_called_once_with()
        client.get_shared_regions.assert_not_called()

    @pytest.mark.parametrize(
        "permissions,missing",
        [
            (["write:sandboxes", "delete:sandboxes"], "read:limits"),
            (["write:sandboxes", "read:limits"], "delete:sandboxes"),
            (["delete:sandboxes", "read:limits"], "write:sandboxes"),
        ],
    )
    def test_validate_config_reports_missing_permissions(
        self, requests_mock, permissions, missing
    ):
        requests_mock.get(f"{API_URL}/api-keys/current", json={"permissions": permissions})
        config = DaytonaBackendConfigWithCreds(creds=DaytonaCreds(api_key="test-key"))

        with pytest.raises(BackendInvalidCredentialsError) as exc:
            DaytonaConfigurator().validate_config(config, default_creds_enabled=False)

        assert exc.value.msg == f"Daytona API key is missing permissions: {missing}"
        assert exc.value.fields == [["creds", "api_key"]]
        assert requests_mock.call_count == 1

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
