import pytest
from packaging.version import Version

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.volumes import (
    RunpodGlobalVolumeConfiguration,
    VolumeProvisioningData,
    VolumeStatus,
)
from dstack._internal.server.compatibility.volumes import patch_volume
from dstack._internal.server.testing.common import get_volume


class TestPatchVolume:
    @pytest.mark.parametrize(
        ("client_version", "has_provisioning_data"),
        [
            (Version("0.22.1"), False),
            (Version("0.22.2"), True),
            (Version("0.22.10"), True),
            (None, True),
        ],
    )
    def test_provisioned_global_volume(self, client_version, has_provisioning_data):
        provisioning_data = VolumeProvisioningData(
            backend=BackendType.RUNPOD,
            volume_id="global-1",
            size_gb=None,
            attachable=False,
            detachable=False,
        )
        volume = get_volume(
            configuration=RunpodGlobalVolumeConfiguration(global_=True),
            volume_id=provisioning_data.volume_id,
            provisioning_data=provisioning_data,
        )

        patch_volume(volume, client_version)

        # Clients before 0.22.2 require an integer capacity, but allow absent provisioning data.
        assert volume.provisioning_data == (provisioning_data if has_provisioning_data else None)
        assert volume.volume_id == "global-1"
        assert volume.status == VolumeStatus.ACTIVE
