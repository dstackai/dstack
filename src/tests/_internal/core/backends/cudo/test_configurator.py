from unittest.mock import patch

import pytest

from dstack._internal.core.backends.cudo.configurator import CudoConfigurator
from dstack._internal.core.backends.cudo.models import CudoBackendConfigWithCreds, CudoCreds
from dstack._internal.core.errors import BackendInvalidCredentialsError


class TestCudoConfigurator:
    def test_validate_config_valid(self):
        config = CudoBackendConfigWithCreds(
            creds=CudoCreds(api_key="valid"),
            project_id="project1",
            regions=["no-luster-1"],
        )
        with patch(
            "dstack._internal.core.backends.cudo.api_client.CudoApiClient.validate_api_key"
        ) as validate_mock:
            validate_mock.return_value = True
            CudoConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = CudoBackendConfigWithCreds(
            creds=CudoCreds(api_key="invalid"),
            project_id="project1",
            regions=["no-luster-1"],
        )
        with (
            patch(
                "dstack._internal.core.backends.cudo.api_client.CudoApiClient.validate_api_key"
            ) as validate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            validate_mock.return_value = False
            CudoConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "api_key"]]
