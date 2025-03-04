from unittest.mock import patch

import pytest

from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends.vastai import VastAIConfigInfoWithCreds, VastAICreds
from dstack._internal.server.services.backends.configurators.vastai import VastAIConfigurator


class TestVastAIConfigurator:
    def test_validate_config_valid(self):
        config = VastAIConfigInfoWithCreds(
            creds=VastAICreds(api_key="valid"),
        )
        with patch(
            "dstack._internal.core.backends.vastai.api_client.VastAIAPIClient.auth_test"
        ) as auth_test_mock:
            auth_test_mock.return_value = True
            VastAIConfigurator().validate_config(config)

    def test_validate_config_invalid_creds(self):
        config = VastAIConfigInfoWithCreds(
            creds=VastAICreds(api_key="invalid"),
        )
        with (
            patch(
                "dstack._internal.core.backends.vastai.api_client.VastAIAPIClient.auth_test"
            ) as auth_test_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            auth_test_mock.return_value = False
            VastAIConfigurator().validate_config(config)
        assert exc_info.value.fields == [["creds", "api_key"]]
