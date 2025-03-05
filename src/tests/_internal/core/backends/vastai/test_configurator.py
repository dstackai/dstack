from unittest.mock import patch

import pytest

from dstack._internal.core.backends.vastai.configurator import VastAIConfigurator
from dstack._internal.core.backends.vastai.models import VastAIBackendConfigWithCreds, VastAICreds
from dstack._internal.core.errors import BackendInvalidCredentialsError


class TestVastAIConfigurator:
    def test_validate_config_valid(self):
        config = VastAIBackendConfigWithCreds(
            creds=VastAICreds(api_key="valid"),
        )
        with patch(
            "dstack._internal.core.backends.vastai.api_client.VastAIAPIClient.auth_test"
        ) as auth_test_mock:
            auth_test_mock.return_value = True
            VastAIConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = VastAIBackendConfigWithCreds(
            creds=VastAICreds(api_key="invalid"),
        )
        with (
            patch(
                "dstack._internal.core.backends.vastai.api_client.VastAIAPIClient.auth_test"
            ) as auth_test_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            auth_test_mock.return_value = False
            VastAIConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "api_key"]]
