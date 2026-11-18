from unittest.mock import Mock

import pytest

from dstack._internal.core.backends.nebius import configurator as configurator_module
from dstack._internal.core.backends.nebius.configurator import NebiusConfigurator
from dstack._internal.core.backends.nebius.models import (
    NebiusBackendConfigWithCreds,
    NebiusServiceAccountCreds,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError


def make_config() -> NebiusBackendConfigWithCreds:
    return NebiusBackendConfigWithCreds(
        creds=NebiusServiceAccountCreds(
            service_account_id="service-account-id",
            public_key_id="public-key-id",
            private_key_content="private-key",
        )
    )


class TestValidateConfig:
    @pytest.fixture(autouse=True)
    def _mock_fabrics(self, mocker):
        mocker.patch.object(configurator_module, "get_all_infiniband_fabrics", return_value=set())

    def test_closes_sdk_if_valid(self, mocker):
        sdk = Mock()
        mocker.patch.object(configurator_module.resources, "make_sdk", return_value=sdk)
        mocker.patch.object(
            configurator_module.resources, "get_region_to_project_id_map", return_value={}
        )
        NebiusConfigurator().validate_config(make_config(), default_creds_enabled=False)
        sdk.sync_close.assert_called_once()

    def test_closes_sdk_if_invalid(self, mocker):
        sdk = Mock()
        mocker.patch.object(configurator_module.resources, "make_sdk", return_value=sdk)
        mocker.patch.object(
            configurator_module.resources,
            "get_region_to_project_id_map",
            side_effect=ValueError("Expected to find 1 tenant, found 0"),
        )
        with pytest.raises(BackendInvalidCredentialsError):
            NebiusConfigurator().validate_config(make_config(), default_creds_enabled=False)
        sdk.sync_close.assert_called_once()
