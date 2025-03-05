from unittest.mock import patch

import pytest

from dstack._internal.core.backends.lambdalabs.configurator import LambdaConfigurator
from dstack._internal.core.backends.lambdalabs.models import (
    LambdaBackendConfigWithCreds,
    LambdaCreds,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError


class TestLambdaConfigurator:
    def test_validate_config_valid(self):
        config = LambdaBackendConfigWithCreds(
            creds=LambdaCreds(api_key="valid"),
            regions=["us-east-1"],
        )
        with patch(
            "dstack._internal.core.backends.lambdalabs.api_client.LambdaAPIClient.validate_api_key"
        ) as validate_mock:
            validate_mock.return_value = True
            LambdaConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = LambdaBackendConfigWithCreds(
            creds=LambdaCreds(api_key="invalid"),
            regions=["us-east-1"],
        )
        with (
            patch(
                "dstack._internal.core.backends.lambdalabs.api_client.LambdaAPIClient.validate_api_key"
            ) as validate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            validate_mock.return_value = False
            LambdaConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "api_key"]]
