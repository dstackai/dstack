from unittest.mock import Mock, patch

import pytest

from dstack._internal.core.backends.gcp.configurator import GCPConfigurator
from dstack._internal.core.backends.gcp.models import (
    GCPBackendConfigWithCreds,
    GCPServiceAccountCreds,
)
from dstack._internal.core.errors import (
    BackendAuthError,
    BackendInvalidCredentialsError,
    ServerClientError,
)


class TestGCPConfigurator:
    def test_validate_config_valid(self):
        config = GCPBackendConfigWithCreds(
            creds=GCPServiceAccountCreds(data="valid", filename="-"),
            project_id="valid-project",
            regions=["us-west1"],
        )
        with (
            patch("dstack._internal.core.backends.gcp.auth.authenticate") as authenticate_mock,
            patch("dstack._internal.core.backends.gcp.resources.check_vpc"),
        ):
            authenticate_mock.return_value = Mock(), Mock()
            GCPConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_valid_subnetworks(self):
        config = GCPBackendConfigWithCreds(
            creds=GCPServiceAccountCreds(data="valid", filename="-"),
            project_id="valid-project",
            regions=["us-west1", "europe-west4"],
            vpc_name="my-vpc",
            subnetworks={"us-west1": "my-subnet"},
        )
        with (
            patch("dstack._internal.core.backends.gcp.auth.authenticate") as authenticate_mock,
            patch("dstack._internal.core.backends.gcp.resources.check_vpc") as check_vpc_mock,
        ):
            authenticate_mock.return_value = Mock(), Mock()
            GCPConfigurator().validate_config(config, default_creds_enabled=True)
        assert check_vpc_mock.call_args.kwargs["subnetworks"] == {"us-west1": "my-subnet"}

    def test_validate_config_subnetworks_without_vpc_name(self):
        config = GCPBackendConfigWithCreds(
            creds=GCPServiceAccountCreds(data="valid", filename="-"),
            project_id="valid-project",
            regions=["us-west1"],
            subnetworks={"us-west1": "my-subnet"},
        )
        with (
            patch("dstack._internal.core.backends.gcp.auth.authenticate") as authenticate_mock,
            pytest.raises(ServerClientError, match="`vpc_name` must be specified"),
        ):
            authenticate_mock.return_value = Mock(), Mock()
            GCPConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_subnetworks_region_not_in_regions(self):
        config = GCPBackendConfigWithCreds(
            creds=GCPServiceAccountCreds(data="valid", filename="-"),
            project_id="valid-project",
            regions=["us-west1"],
            vpc_name="my-vpc",
            subnetworks={"europe-west4": "my-subnet"},
        )
        with (
            patch("dstack._internal.core.backends.gcp.auth.authenticate") as authenticate_mock,
            pytest.raises(ServerClientError, match="regions not in `regions`"),
        ):
            authenticate_mock.return_value = Mock(), Mock()
            GCPConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = GCPBackendConfigWithCreds(
            creds=GCPServiceAccountCreds(data="invalid", filename="-"),
            project_id="invalid-project",
            regions=["us-west1"],
        )
        with (
            patch("dstack._internal.core.backends.gcp.auth.authenticate") as authenticate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            authenticate_mock.side_effect = BackendAuthError()
            GCPConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "data"]]
