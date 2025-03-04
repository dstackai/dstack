from unittest.mock import patch

import pytest

from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends.tensordock import (
    TensorDockConfigInfoWithCreds,
    TensorDockCreds,
)
from dstack._internal.server.services.backends.configurators.tensordock import (
    TensorDockConfigurator,
)


class TestTensorDockConfigurator:
    def test_validate_config_valid(self):
        config = TensorDockConfigInfoWithCreds(
            creds=TensorDockCreds(api_key="valid", api_token="valid"),
        )
        with patch(
            "dstack._internal.core.backends.tensordock.api_client.TensorDockAPIClient.auth_test"
        ) as auth_test_mock:
            auth_test_mock.return_value = True
            TensorDockConfigurator().validate_config(config)

    def test_validate_config_invalid_creds(self):
        config = TensorDockConfigInfoWithCreds(
            creds=TensorDockCreds(api_key="invalid", api_token="invalid"),
        )
        with (
            patch(
                "dstack._internal.core.backends.tensordock.api_client.TensorDockAPIClient.auth_test"
            ) as auth_test_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            auth_test_mock.return_value = False
            TensorDockConfigurator().validate_config(config)
        assert exc_info.value.fields == [["creds", "api_key"], ["creds", "api_token"]]
