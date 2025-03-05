from unittest.mock import patch

import pytest

from dstack._internal.core.backends.tensordock.configurator import (
    TensorDockConfigurator,
)
from dstack._internal.core.backends.tensordock.models import (
    TensorDockBackendConfigWithCreds,
    TensorDockCreds,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError


class TestTensorDockConfigurator:
    def test_validate_config_valid(self):
        config = TensorDockBackendConfigWithCreds(
            creds=TensorDockCreds(api_key="valid", api_token="valid"),
        )
        with patch(
            "dstack._internal.core.backends.tensordock.api_client.TensorDockAPIClient.auth_test"
        ) as auth_test_mock:
            auth_test_mock.return_value = True
            TensorDockConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = TensorDockBackendConfigWithCreds(
            creds=TensorDockCreds(api_key="invalid", api_token="invalid"),
        )
        with (
            patch(
                "dstack._internal.core.backends.tensordock.api_client.TensorDockAPIClient.auth_test"
            ) as auth_test_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            auth_test_mock.return_value = False
            TensorDockConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "api_key"], ["creds", "api_token"]]
