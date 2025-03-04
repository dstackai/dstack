from unittest.mock import patch

import pytest

from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends.lambdalabs import (
    LambdaConfigInfoWithCreds,
    LambdaCreds,
)
from dstack._internal.server.services.backends.configurators.lambdalabs import LambdaConfigurator


class TestLambdaConfigurator:
    def test_validate_config_valid(self):
        config = LambdaConfigInfoWithCreds(
            creds=LambdaCreds(api_key="valid"),
            regions=["us-east-1"],
        )
        with patch(
            "dstack._internal.core.backends.lambdalabs.api_client.LambdaAPIClient.validate_api_key"
        ) as validate_mock:
            validate_mock.return_value = True
            LambdaConfigurator().validate_config(config)

    def test_validate_config_invalid_creds(self):
        config = LambdaConfigInfoWithCreds(
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
            LambdaConfigurator().validate_config(config)
        assert exc_info.value.fields == [["creds", "api_key"]]
