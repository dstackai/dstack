import pytest
from pydantic import ValidationError, parse_obj_as

from dstack._internal.core.models.volumes import InstanceMountPoint, VolumeMountPoint


class TestVolumeMountPoint:
    def test_parse(self):
        assert VolumeMountPoint.parse("my-vol:/path/./to///dir/") == VolumeMountPoint(
            name="my-vol", path="/path/to/dir"
        )

    def test_path_normalization(self):
        assert parse_obj_as(
            VolumeMountPoint, {"name": "my-vol", "path": "/path/./to///dir/"}
        ) == VolumeMountPoint(name="my-vol", path="/path/to/dir")

    @pytest.mark.parametrize(
        "value",
        [
            "vol",
            "vol:/path/to:ro",
        ],
    )
    def test_parse_error_invalid_format(self, value: str):
        with pytest.raises(ValueError, match="invalid mount point format"):
            VolumeMountPoint.parse(value)

    def test_validation_error_empty_path(self):
        with pytest.raises(ValidationError, match="empty path"):
            parse_obj_as(VolumeMountPoint, {"name": "vol", "path": ""})

    def test_validation_error_rel_path(self):
        with pytest.raises(ValidationError, match="path must be absolute"):
            parse_obj_as(VolumeMountPoint, {"name": "vol", "path": "rel/path"})

    def test_validation_error_parent_dir(self):
        with pytest.raises(ValidationError, match=r"\.\. are not allowed"):
            parse_obj_as(VolumeMountPoint, {"name": "vol", "path": "/path/../to"})


class TestInstanceBindMountPoint:
    def test_parse(self):
        assert InstanceMountPoint.parse("/host/.//path/:/run//./path") == InstanceMountPoint(
            instance_path="/host/path", path="/run/path"
        )

    def test_path_normalization(self):
        assert parse_obj_as(
            InstanceMountPoint, {"instance_path": "/host/.//path/", "path": "/run//./path"}
        ) == InstanceMountPoint(instance_path="/host/path", path="/run/path")

    @pytest.mark.parametrize(
        "value",
        [
            "/path",
            "/host/path:/run/path:ro",
        ],
    )
    def test_parse_error_invalid_format(self, value: str):
        with pytest.raises(ValueError, match="invalid mount point format"):
            InstanceMountPoint.parse(value)

    @pytest.mark.parametrize("field", ["instance_path", "path"])
    def test_validation_error_empty_path(self, field: str):
        data = {"instance_path": "/instance_path", "path": "/run_path"}
        data[field] = ""
        with pytest.raises(ValidationError, match="empty path"):
            parse_obj_as(InstanceMountPoint, data)

    @pytest.mark.parametrize("field", ["instance_path", "path"])
    def test_validation_error_rel_path(self, field: str):
        data = {"instance_path": "/instance_path", "path": "/run_path"}
        data[field] = "./rel/path"
        with pytest.raises(ValidationError, match="path must be absolute"):
            parse_obj_as(InstanceMountPoint, data)

    @pytest.mark.parametrize("field", ["instance_path", "path"])
    def test_validation_error_parent_dir(self, field: str):
        data = {"instance_path": "/instance_path", "path": "/run_path"}
        data[field] = "/path/../to"
        with pytest.raises(ValidationError, match=r"\.\. are not allowed"):
            parse_obj_as(InstanceMountPoint, data)
