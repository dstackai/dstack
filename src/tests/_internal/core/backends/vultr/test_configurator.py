from unittest.mock import patch

import pytest

from dstack._internal.core.backends.vultr.configurator import VultrConfigurator
from dstack._internal.core.backends.vultr.models import VultrBackendConfigWithCreds, VultrCreds
from dstack._internal.core.errors import BackendInvalidCredentialsError


class TestVultrConfigurator:
    def test_validate_config_valid(self):
        config = VultrBackendConfigWithCreds(
            creds=VultrCreds(api_key="valid"),
        )
        with patch(
            "dstack._internal.core.backends.vultr.api_client.VultrApiClient.validate_api_key"
        ) as validate_mock:
            validate_mock.return_value = True
            VultrConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = VultrBackendConfigWithCreds(
            creds=VultrCreds(api_key="invalid"),
        )
        with (
            patch(
                "dstack._internal.core.backends.vultr.api_client.VultrApiClient.validate_api_key"
            ) as validate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            validate_mock.return_value = False
            VultrConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "api_key"]]
