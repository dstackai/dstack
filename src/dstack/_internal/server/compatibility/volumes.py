from typing import Optional

from packaging.version import Version

from dstack._internal.core.models.volumes import (
    RunpodGlobalVolumeConfiguration,
    RunpodVolumeConfiguration,
    Volume,
)


def patch_volume(volume: Volume, client_version: Optional[Version]) -> None:
    if client_version is None or client_version >= Version("0.22.10"):
        return
    if isinstance(volume.configuration, RunpodGlobalVolumeConfiguration):
        if client_version < Version("0.22.2"):
            # These clients require a fixed capacity, but allow absent provisioning data.
            volume.provisioning_data = None
        # Older clients require a Runpod region even when only displaying a volume.
        # Keep listing/get working; configuring global volumes requires a newer client.
        volume.configuration = RunpodVolumeConfiguration(
            **volume.configuration.model_dump(exclude={"global_"}), region=""
        )
