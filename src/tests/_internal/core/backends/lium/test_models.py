import pytest
from pydantic import Field, TypeAdapter, ValidationError
from typing_extensions import Annotated

from dstack._internal.core.backends.lium.models import LiumBackendConfigWithCreds
from dstack._internal.core.backends.models import (
    AnyBackendFileConfigWithCreds,
    BackendConfigWithCreds,
)
from dstack._internal.core.models.volumes import LiumVolumeConfiguration, VolumeConfiguration


class TestLiumBackendConfig:
    def test_api_and_server_file_configs_accept_lium(self):
        data = {
            "type": "lium",
            "regions": ["us-ia", "de-he"],
            "creds": {"type": "api_key", "api_key": "test-key"},
        }
        api_config = BackendConfigWithCreds.model_validate(data).root
        file_config = TypeAdapter(
            Annotated[AnyBackendFileConfigWithCreds, Field(discriminator="type")]
        ).validate_python(data)

        assert isinstance(api_config, LiumBackendConfigWithCreds)
        assert api_config == file_config
        assert api_config.regions == ["us-ia", "de-he"]


class TestLiumVolumeConfiguration:
    @pytest.mark.parametrize("volume_id", [None, "volume-id"])
    def test_accepts_unbounded_volumes_without_region(self, volume_id):
        config = VolumeConfiguration.model_validate(
            {"backend": "lium", "volume_id": volume_id}
        ).root

        assert isinstance(config, LiumVolumeConfiguration)
        assert config.is_external == (volume_id is not None)
        assert config.external_volume_id == volume_id

    @pytest.mark.parametrize("field,value", [("size", "100GB"), ("region", "us-ia")])
    def test_rejects_unsupported_size_and_region(self, field, value):
        with pytest.raises(ValidationError):
            VolumeConfiguration.model_validate({"backend": "lium", field: value})
