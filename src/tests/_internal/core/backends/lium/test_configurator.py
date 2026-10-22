import json
from unittest.mock import patch

import pytest

from dstack._internal.core.backends.lium.api_client import API_URL, LiumAPIError
from dstack._internal.core.backends.lium.configurator import LiumConfigurator
from dstack._internal.core.backends.lium.models import LiumBackendConfigWithCreds, LiumCreds
from dstack._internal.core.errors import BackendInvalidCredentialsError


class TestLiumConfigurator:
    def test_validate_config(self):
        config = LiumBackendConfigWithCreds(creds=LiumCreds(api_key="test-key"))
        with patch(
            "dstack._internal.core.backends.lium.configurator.LiumAPIClient", autospec=True
        ) as client:
            LiumConfigurator().validate_config(config, default_creds_enabled=False)

        client.assert_called_once_with("test-key")
        client.return_value.get_user.assert_called_once_with()

    def test_invalid_credentials(self, requests_mock):
        requests_mock.get(f"{API_URL}/users/me", status_code=401)
        config = LiumBackendConfigWithCreds(creds=LiumCreds(api_key="invalid"))

        with pytest.raises(BackendInvalidCredentialsError) as exc:
            LiumConfigurator().validate_config(config, default_creds_enabled=False)

        assert exc.value.fields == [["creds", "api_key"]]

    def test_server_error_is_not_invalid_credentials(self, requests_mock):
        requests_mock.get(f"{API_URL}/users/me", status_code=503)
        config = LiumBackendConfigWithCreds(creds=LiumCreds(api_key="test-key"))

        with pytest.raises(LiumAPIError):
            LiumConfigurator().validate_config(config, default_creds_enabled=False)

    def test_stored_config_keeps_credentials_separate(self):
        config = LiumBackendConfigWithCreds(
            creds=LiumCreds(api_key="test-secret"), regions=["us-ia", "de-he"]
        )
        configurator = LiumConfigurator()

        record = configurator.create_backend(project_name="main", config=config)

        assert json.loads(record.config) == {"type": "lium", "regions": ["us-ia", "de-he"]}
        assert json.loads(record.auth) == {"type": "api_key", "api_key": "test-secret"}
        assert configurator.get_backend_config_with_creds(record) == config
        public_config = configurator.get_backend_config_without_creds(record).model_dump()
        assert public_config == json.loads(record.config)
