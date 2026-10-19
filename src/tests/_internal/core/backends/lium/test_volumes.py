from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from dstack._internal.core.backends.lium.api_client import LiumAPIError
from dstack._internal.core.backends.lium.compute import LiumCompute, _get_volume_commands
from dstack._internal.core.backends.lium.models import LiumConfig, LiumCreds
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.unix import UnixUser
from dstack._internal.core.models.volumes import LiumVolumeConfiguration, VolumeMountPoint

COMPUTE_MODULE = "dstack._internal.core.backends.lium.compute"


@pytest.fixture
def compute():
    compute = LiumCompute(LiumConfig(creds=LiumCreds(api_key="test-key")))
    compute.api_client = Mock()
    return compute


class TestVolumeLifecycle:
    def test_create_unbounded_volume(self, compute):
        compute.api_client.create_volume.return_value = {"id": "volume-id"}
        with patch(f"{COMPUTE_MODULE}.generate_unique_volume_name", return_value="unique-name"):
            data = compute.create_volume(Mock())

        compute.api_client.create_volume.assert_called_once_with("unique-name")
        assert data.volume_id == "volume-id"
        assert data.size_gb is None
        assert data.price is None
        assert not data.attachable
        assert not data.detachable

    def test_recovers_lost_create_response_by_unique_name(self, compute):
        compute.api_client.create_volume.side_effect = LiumAPIError("timed out")
        compute.api_client.get_volumes.return_value = [
            {"id": "other-id", "name": "other"},
            {"id": "volume-id", "name": "unique-name"},
        ]
        with patch(f"{COMPUTE_MODULE}.generate_unique_volume_name", return_value="unique-name"):
            data = compute.create_volume(Mock())

        assert data.volume_id == "volume-id"
        assert compute.api_client.create_volume.call_count == 1

    def test_register_existing_volume(self, compute):
        volume = SimpleNamespace(configuration=LiumVolumeConfiguration(volume_id="existing"))
        compute.api_client.get_volume.return_value = {"id": "existing"}

        data = compute.register_volume(volume)

        assert data.volume_id == "existing"
        compute.api_client.create_volume.assert_not_called()

    def test_register_missing_volume(self, compute):
        compute.api_client.get_volume.return_value = None
        with pytest.raises(ComputeError, match="not found"):
            compute.register_volume(
                SimpleNamespace(configuration=LiumVolumeConfiguration(volume_id="missing"))
            )

    def test_delete_volume(self, compute):
        compute.delete_volume(SimpleNamespace(volume_id="volume-id"))
        compute.api_client.delete_volume.assert_called_once_with("volume-id")


class TestVolumeMount:
    @pytest.mark.parametrize(
        "user",
        [
            None,
            UnixUser(uid=0),
            UnixUser(username="root"),
            UnixUser(uid=10001),
            UnixUser(username="app"),
        ],
    )
    def test_custom_path(self, user):
        commands = _volume_commands(user=user, path="/checkpoints")

        assert commands[0] == "grep -q ' /mnt .* - fuse.s3fs ' /proc/self/mountinfo"
        assert commands[1:] == ["mkdir -p -- /checkpoints", "mount --bind /mnt /checkpoints"]

    def test_native_mount_path_needs_no_bind(self):
        assert len(_volume_commands(path="/mnt")) == 1

    def test_quotes_mount_path(self):
        commands = _volume_commands(path="/checkpoint dir; echo unsafe")
        assert commands[-1] == "mount --bind /mnt '/checkpoint dir; echo unsafe'"

    @pytest.mark.parametrize("path", ["/", "/root", "/root/.dstack-lium", "/proc/a", "/mnt/a"])
    def test_rejects_paths_that_hide_bootstrap_or_nest_source(self, path):
        with pytest.raises(ComputeError, match="cannot be mounted"):
            _volume_commands(path=path)

    def test_two_volumes_rejected(self):
        with pytest.raises(ComputeError, match="only one"):
            _get_volume_commands(Mock(), Mock(), [Mock(), Mock()])

    def test_selects_volume_from_alternatives(self):
        job = SimpleNamespace(
            job_spec=SimpleNamespace(
                user=None,
                volumes=[VolumeMountPoint(name=["elsewhere", "cache"], path="/data")],
            )
        )
        assert _get_volume_commands(Mock(), job, [SimpleNamespace(name="cache")])[-1] == (
            "mount --bind /mnt /data"
        )


def _volume_commands(user=None, path="/checkpoints"):
    job = SimpleNamespace(
        job_spec=SimpleNamespace(user=user, volumes=[VolumeMountPoint(name="cache", path=path)])
    )
    return _get_volume_commands(Mock(), job, [SimpleNamespace(name="cache")])
