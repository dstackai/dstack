from unittest.mock import patch

import pytest

from dstack._internal.core.errors import (
    BackendAuthError,
    BackendInvalidCredentialsError,
)
from dstack._internal.core.models.backends.aws import AWSAccessKeyCreds, AWSConfigInfoWithCreds
from dstack._internal.server.services.backends.configurators.aws import AWSConfigurator


class TestAWSConfigurator:
    def test_validate_config_valid(self):
        config = AWSConfigInfoWithCreds(
            creds=AWSAccessKeyCreds(access_key="valid", secret_key="valid"), regions=["us-west-1"]
        )
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"),
        ):
            AWSConfigurator().validate_config(config)

    def test_validate_config_invalid_creds(self):
        config = AWSConfigInfoWithCreds(
            creds=AWSAccessKeyCreds(access_key="invalid", secret_key="invalid"),
            regions=["us-west-1"],
        )
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate") as authenticate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            authenticate_mock.side_effect = BackendAuthError()
            AWSConfigurator().validate_config(config)
        assert exc_info.value.fields == [["creds", "access_key"], ["creds", "secret_key"]]
