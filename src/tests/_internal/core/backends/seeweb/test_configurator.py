from unittest.mock import patch

import pytest

from dstack._internal.core.backends.configurators import (
    get_configurator,
    list_available_backend_types,
)
from dstack._internal.core.backends.seeweb.backend import SeewebBackend
from dstack._internal.core.backends.seeweb.compute import SeewebCompute
from dstack._internal.core.backends.seeweb.configurator import SeewebConfigurator
from dstack._internal.core.backends.seeweb.models import (
    SeewebAPITokenCreds,
    SeewebBackendConfigWithCreds,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends.base import BackendType

VALIDATE = "dstack._internal.core.backends.seeweb.api_client.SeewebApiClient.validate_api_key"


class TestSeewebConfigurator:
    def test_registered(self):
        assert BackendType.SEEWEB in list_available_backend_types()
        assert isinstance(get_configurator(BackendType.SEEWEB), SeewebConfigurator)

    def test_validate_config_valid(self):
        config = SeewebBackendConfigWithCreds(
            creds=SeewebAPITokenCreds(api_token="valid"),
            regions=["it-mi2"],
        )
        with patch(VALIDATE) as validate_mock:
            validate_mock.return_value = True
            SeewebConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = SeewebBackendConfigWithCreds(
            creds=SeewebAPITokenCreds(api_token="invalid"),
            regions=["it-mi2"],
        )
        with (
            patch(VALIDATE) as validate_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            validate_mock.return_value = False
            SeewebConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds", "api_token"]]

    def test_config_round_trip_strips_creds(self):
        config = SeewebBackendConfigWithCreds(
            creds=SeewebAPITokenCreds(api_token="secret-token"),
            regions=["it-mi2", "it-fr2"],
        )
        configurator = SeewebConfigurator()
        record = configurator.create_backend("proj", config)

        # Creds are stored separately from the non-sensitive config.
        assert "secret-token" not in record.config
        assert "secret-token" in record.auth

        with_creds = configurator.get_backend_config_with_creds(record)
        assert with_creds.creds.api_token == "secret-token"
        assert with_creds.regions == ["it-mi2", "it-fr2"]

        without_creds = configurator.get_backend_config_without_creds(record)
        assert not hasattr(without_creds, "creds")

        backend = configurator.get_backend(record)
        assert isinstance(backend, SeewebBackend)
        assert isinstance(backend.compute(), SeewebCompute)
