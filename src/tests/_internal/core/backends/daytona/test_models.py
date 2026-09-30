from pydantic import Field, TypeAdapter
from typing_extensions import Annotated

from dstack._internal.core.backends.daytona.models import DaytonaBackendConfigWithCreds
from dstack._internal.core.backends.models import (
    AnyBackendFileConfigWithCreds,
    BackendConfigWithCreds,
)


class TestDaytonaBackendConfig:
    def test_api_and_server_file_configs_accept_daytona(self):
        data = {
            "type": "daytona",
            "regions": ["earth", "eu"],
            "creds": {"type": "api_key", "api_key": "test-key"},
        }
        api_config = BackendConfigWithCreds.model_validate(data).root
        file_config = TypeAdapter(
            Annotated[AnyBackendFileConfigWithCreds, Field(discriminator="type")]
        ).validate_python(data)

        assert isinstance(api_config, DaytonaBackendConfigWithCreds)
        assert api_config == file_config
        assert api_config.regions == ["earth", "eu"]
        assert api_config.creds.api_key == "test-key"
