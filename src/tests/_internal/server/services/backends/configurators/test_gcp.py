from unittest.mock import Mock, patch

import pytest

from dstack._internal.core.errors import (
    BackendAuthError,
    BackendInvalidCredentialsError,
)
from dstack._internal.core.models.backends.gcp import (
    GCPConfigInfoWithCreds,
    GCPServiceAccountCreds,
)
from dstack._internal.server.services.backends.configurators.gcp import GCPConfigurator


class TestGCPConfigurator:
    def test_validate_config_valid(self):
        config = GCPConfigInfoWithCreds(
            creds=GCPServiceAccountCreds(data="valid", filename="-"),
            project_id="valid-project",
            regions=["us-west1"],
        )
        with (
            patch("dstack._internal.core.backends.gcp.auth.authenticate") as authenticate_mock,
            patch("dstack._internal.core.backends.gcp.resources.check_vpc"),
        ):
            authenticate_mock.return_value = Mock(), Mock()
            GCPConfigurator().validate_config(config)

    def test_validate_config_invalid_creds(self):
        config = GCPConfigInfoWithCreds(
            creds=GCPServiceAccountCreds(data="invalid", filename="-"),
            project_id="invalid-project",
            regions=["us-west1"],
        )
        with (
            patch("dstack._internal.core.backends.gcp.auth.authenticate") as authenticate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            authenticate_mock.side_effect = BackendAuthError()
            GCPConfigurator().validate_config(config)
        assert exc_info.value.fields == [["creds", "data"]]
