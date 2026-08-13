from unittest.mock import Mock

import gpuhunt
import pytest

from dstack._internal.server.services.docker import ImageConfig, ImageConfigObject


@pytest.fixture
def image_config_mock(monkeypatch: pytest.MonkeyPatch) -> ImageConfig:
    image_config = ImageConfig.model_validate(
        {"User": None, "Entrypoint": None, "Cmd": ["/bin/bash"]}
    )
    monkeypatch.setattr(
        "dstack._internal.server.services.jobs.configurators.base"
        "._get_image_config_and_cpu_architectures",
        Mock(return_value=(image_config, {gpuhunt.CPUArchitecture.X86})),
    )
    monkeypatch.setattr(
        "dstack._internal.server.services.docker.get_image_config_and_cpu_architectures",
        Mock(
            return_value=(
                ImageConfigObject(architecture="amd64", os="linux", config=image_config),
                {gpuhunt.CPUArchitecture.X86},
            )
        ),
    )
    return image_config
