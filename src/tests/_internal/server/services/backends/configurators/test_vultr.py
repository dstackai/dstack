from unittest.mock import patch

import pytest

from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends.vultr import VultrConfigInfoWithCreds, VultrCreds
from dstack._internal.server.services.backends.configurators.vultr import VultrConfigurator


class TestVultrConfigurator:
    def test_validate_config_valid(self):
        config = VultrConfigInfoWithCreds(
            creds=VultrCreds(api_key="valid"),
        )
        with patch(
            "dstack._internal.core.backends.vultr.api_client.VultrApiClient.validate_api_key"
        ) as validate_mock:
            validate_mock.return_value = True
            VultrConfigurator().validate_config(config)

    def test_validate_config_invalid_creds(self):
        config = VultrConfigInfoWithCreds(
            creds=VultrCreds(api_key="invalid"),
        )
        with (
            patch(
                "dstack._internal.core.backends.vultr.api_client.VultrApiClient.validate_api_key"
            ) as validate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            validate_mock.return_value = False
            VultrConfigurator().validate_config(config)
        assert exc_info.value.fields == [["creds", "api_key"]]
