from unittest.mock import Mock

import pytest

from dstack._internal.server.services.docker import ImageConfig, ImageConfigObject


@pytest.fixture
def image_config_mock(monkeypatch: pytest.MonkeyPatch) -> ImageConfig:
    image_config = ImageConfig.parse_obj({"User": None, "Entrypoint": None, "Cmd": ["/bin/bash"]})
    monkeypatch.setattr(
        "dstack._internal.server.services.jobs.configurators.base._get_image_config",
        Mock(return_value=image_config),
    )
    monkeypatch.setattr(
        "dstack._internal.server.services.docker.get_image_config",
        Mock(return_value=ImageConfigObject(config=image_config)),
    )
    return image_config
