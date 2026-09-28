import json

import pytest
from pydantic import ValidationError

from dstack._internal.core.models.volumes import (
    DaytonaVolumeConfiguration,
    InstanceMountPoint,
    VolumeConfiguration,
    VolumeConfigurationWithSize,
    VolumeMountPoint,
    VolumeProvisioningData,
    VolumeSpec,
    parse_mount_point,
)


@pytest.mark.parametrize("backend", ["aws", "gcp", "runpod", "kubernetes"])
class TestSizedVolumeConfiguration:
    def test_managed_size_keeps_numeric_wire_format(self, backend):
        spec = VolumeSpec.model_validate(
            {"configuration": {"backend": backend, "region": "us", "size": "120GB"}}
        )

        assert isinstance(spec.configuration, VolumeConfigurationWithSize)
        assert spec.configuration.size_gb == 120
        assert not spec.configuration.is_external
        assert json.loads(spec.model_dump_json())["configuration"]["size"] == 120.0
        restored = VolumeSpec.model_validate_json(spec.model_dump_json())
        assert restored == spec


class TestDaytonaVolumeConfiguration:
    @pytest.mark.parametrize("volume_id", [None, "existing-volume"])
    def test_roundtrip_without_region_or_size(self, volume_id):
        spec = VolumeSpec.model_validate(
            {"configuration": {"backend": "daytona", "name": "cache", "volume_id": volume_id}}
        )

        assert isinstance(spec.configuration, DaytonaVolumeConfiguration)
        assert spec.configuration.is_external == (volume_id is not None)
        assert "region" not in spec.configuration.model_dump()
        assert "size" not in spec.configuration.model_dump()
        assert VolumeSpec.model_validate_json(spec.model_dump_json()) == spec

    @pytest.mark.parametrize(("field", "value"), [("size", 100), ("region", "us")])
    def test_rejects_fixed_size_and_region(self, field, value):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            VolumeConfiguration.model_validate({"backend": "daytona", field: value})


class TestVolumeProvisioningData:
    def test_existing_capacity_remains_an_integer(self):
        data = VolumeProvisioningData.model_validate(
            {"backend": "aws", "volume_id": "volume-id", "size_gb": 120}
        )

        payload = json.loads(data.model_dump_json())
        assert type(payload["size_gb"]) is int
        assert payload["size_gb"] == 120
        assert VolumeProvisioningData.model_validate(payload).size_gb == 120

    def test_daytona_capacity_serializes_as_null(self):
        data = VolumeProvisioningData.model_validate(
            {"backend": "daytona", "volume_id": "volume-id", "size_gb": None}
        )

        assert json.loads(data.model_dump_json())["size_gb"] is None


class TestVolumeMountPoint:
    def test_parse(self):
        assert VolumeMountPoint.parse("my-vol:/path/./to///dir/") == VolumeMountPoint(
            name="my-vol", path="/path/to/dir"
        )

    def test_path_normalization(self):
        assert VolumeMountPoint.model_validate(
            {"name": "my-vol", "path": "/path/./to///dir/"}
        ) == VolumeMountPoint(name="my-vol", path="/path/to/dir")

    @pytest.mark.parametrize("value", ["my-vol", "my-vol:/run:ro"])
    def test_parse_error_invalid_format(self, value: str):
        with pytest.raises(ValueError, match="invalid mount point format"):
            VolumeMountPoint.parse(value)

    def test_validation_error_empty_path(self):
        with pytest.raises(ValidationError, match="empty path"):
            VolumeMountPoint.model_validate({"name": "vol", "path": ""})

    def test_validation_error_rel_path(self):
        with pytest.raises(ValidationError, match="path must be absolute"):
            VolumeMountPoint.model_validate({"name": "vol", "path": "rel/path"})

    def test_validation_error_parent_dir(self):
        with pytest.raises(ValidationError, match=r"\.\. are not allowed"):
            VolumeMountPoint.model_validate({"name": "vol", "path": "/path/../to"})


class TestInstanceBindMountPoint:
    def test_parse(self):
        assert InstanceMountPoint.parse("/host/.//path/:/run//./path") == InstanceMountPoint(
            instance_path="/host/path", path="/run/path"
        )

    def test_path_normalization(self):
        assert InstanceMountPoint.model_validate(
            {"instance_path": "/host/.//path/", "path": "/run//./path"}
        ) == InstanceMountPoint(instance_path="/host/path", path="/run/path")

    @pytest.mark.parametrize("value", ["/path", "/host/path:/run/path:ro"])
    def test_parse_error_invalid_format(self, value: str):
        with pytest.raises(ValueError, match="invalid mount point format"):
            InstanceMountPoint.parse(value)

    @pytest.mark.parametrize("field", ["instance_path", "path"])
    def test_validation_error_empty_path(self, field: str):
        data = {"instance_path": "/instance_path", "path": "/run_path"}
        data[field] = ""
        with pytest.raises(ValidationError, match="empty path"):
            InstanceMountPoint.model_validate(data)

    @pytest.mark.parametrize("field", ["instance_path", "path"])
    def test_validation_error_rel_path(self, field: str):
        data = {"instance_path": "/instance_path", "path": "/run_path"}
        data[field] = "./rel/path"
        with pytest.raises(ValidationError, match="path must be absolute"):
            InstanceMountPoint.model_validate(data)

    @pytest.mark.parametrize("field", ["instance_path", "path"])
    def test_validation_error_parent_dir(self, field: str):
        data = {"instance_path": "/instance_path", "path": "/run_path"}
        data[field] = "/path/../to"
        with pytest.raises(ValidationError, match=r"\.\. are not allowed"):
            InstanceMountPoint.model_validate(data)


class TestParseMountPoint:
    def test_parse_volume_mount(self):
        assert parse_mount_point("my-vol:/path//to") == VolumeMountPoint(
            name="my-vol", path="/path/to"
        )

    def test_parse_instance_mount(self):
        assert parse_mount_point("/host:/run/") == InstanceMountPoint(
            instance_path="/host", path="/run"
        )

    @pytest.mark.parametrize(
        "value", ["my-vol", "my-vol:/run:ro", "/path", "/host/path:/run/path:ro"]
    )
    def test_parse_error_invalid_format(self, value: str):
        with pytest.raises(ValueError, match="invalid mount point format"):
            parse_mount_point(value)

    @pytest.mark.parametrize("value", ["path/to:/run", "./path:/run", "path/:/run"])
    def test_validation_error_rel_local_path(self, value: str):
        with pytest.raises(ValidationError, match="path must be absolute"):
            parse_mount_point(value)
