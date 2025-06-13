from unittest.mock import patch

import pytest

from dstack._internal.core.backends.cloudrift.configurator import (
    CloudRiftConfigurator,
)
from dstack._internal.core.backends.cloudrift.models import (
    CloudRiftBackendConfigWithCreds,
    CloudRiftCreds,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError


class TestDataCrunchConfigurator:
    def test_validate_config_valid(self):
        config = CloudRiftBackendConfigWithCreds(creds=CloudRiftCreds(api_key="valid"))
        with patch(
            "dstack._internal.core.backends.cloudrift.api_client.RiftClient.validate_api_key"
        ) as validate_mock:
            validate_mock.return_value = True
            CloudRiftConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid(self):
        config = CloudRiftBackendConfigWithCreds(creds=CloudRiftCreds(api_key="invalid"))
        with (
            patch(
                "dstack._internal.core.backends.cloudrift.api_client.RiftClient.validate_api_key"
            ) as validate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            validate_mock.return_value = False
            CloudRiftConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "api_key"]]
