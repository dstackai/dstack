import pytest

from dstack._internal.core.compatibility.volumes import (
    get_create_volume_excludes,
    get_volume_spec_excludes,
)
from dstack._internal.core.models.volumes import VolumeSpec


class TestVolumeExcludes:
    @pytest.mark.parametrize("global_volume", [False, True])
    def test_runpod_global_is_sent_only_when_enabled(self, global_volume):
        config = (
            {"backend": "runpod", "global": True}
            if global_volume
            else {"backend": "runpod", "region": "EU-CZ-1", "size": "100GB"}
        )
        spec = VolumeSpec.model_validate({"configuration": config})
        for excludes in (
            get_volume_spec_excludes(spec),
            get_create_volume_excludes(spec.configuration),
        ):
            payload = spec.model_dump(exclude=excludes)["configuration"]
            if global_volume:
                assert payload["global"] is True
            else:
                assert "global" not in payload
