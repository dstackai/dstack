from unittest.mock import patch

import pytest

from dstack._internal.core.backends.jarvislabs.configurator import JarvisLabsConfigurator
from dstack._internal.core.backends.jarvislabs.models import (
    JarvisLabsBackendConfigWithCreds,
    JarvisLabsCreds,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError, ServerClientError


class TestJarvisLabsConfigurator:
    def test_validate_config_valid(self):
        config = JarvisLabsBackendConfigWithCreds(
            creds=JarvisLabsCreds(api_key="valid"),
            regions=["india-noida-01"],
        )
        with patch(
            "dstack._internal.core.backends.jarvislabs.api_client.JarvisLabsAPIClient.validate_api_key"
        ) as validate_mock:
            validate_mock.return_value = True
            JarvisLabsConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = JarvisLabsBackendConfigWithCreds(
            creds=JarvisLabsCreds(api_key="invalid"),
            regions=["india-noida-01"],
        )
        with (
            patch(
                "dstack._internal.core.backends.jarvislabs.api_client.JarvisLabsAPIClient.validate_api_key"
            ) as validate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            validate_mock.return_value = False
            JarvisLabsConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "api_key"]]

    def test_validate_config_unsupported_region(self):
        config = JarvisLabsBackendConfigWithCreds(
            creds=JarvisLabsCreds(api_key="valid"),
            regions=["unknown-region"],
        )
        with (
            patch(
                "dstack._internal.core.backends.jarvislabs.api_client.JarvisLabsAPIClient.validate_api_key"
            ) as validate_mock,
            pytest.raises(ServerClientError) as exc_info,
        ):
            validate_mock.return_value = True
            JarvisLabsConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["regions"]]
        assert "Unsupported JarvisLabs regions" in exc_info.value.msg
