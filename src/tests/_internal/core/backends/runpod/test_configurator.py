from unittest.mock import patch

import pytest

from dstack._internal.core.backends.runpod.configurator import RunpodConfigurator
from dstack._internal.core.backends.runpod.models import RunpodBackendConfigWithCreds, RunpodCreds
from dstack._internal.core.errors import BackendInvalidCredentialsError


class TestRunpodConfigurator:
    def test_validate_config_valid(self):
        config = RunpodBackendConfigWithCreds(
            creds=RunpodCreds(api_key="valid"),
        )
        with patch(
            "dstack._internal.core.backends.runpod.api_client.RunpodApiClient.validate_api_key"
        ) as validate_mock:
            validate_mock.return_value = True
            RunpodConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = RunpodBackendConfigWithCreds(
            creds=RunpodCreds(api_key="invalid"),
        )
        with (
            patch(
                "dstack._internal.core.backends.runpod.api_client.RunpodApiClient.validate_api_key"
            ) as validate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            validate_mock.return_value = False
            RunpodConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "api_key"]]
