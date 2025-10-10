import pytest
from pydantic import ValidationError

from dstack._internal.core.models.files import FilePathMapping


class TestFilePathMapping:
    @pytest.mark.parametrize("value", ["./file", "file", "~/file", "/file"])
    def test_parse_only_local_path(self, value: str):
        assert FilePathMapping.parse(value) == FilePathMapping(local_path=value, path=value)

    def test_parse_both_paths(self):
        assert FilePathMapping.parse("./foo:./bar") == FilePathMapping(
            local_path="./foo", path="./bar"
        )

    def test_parse_windows_abs_path(self):
        assert FilePathMapping.parse("C:\\dir:dir") == FilePathMapping(
            local_path="C:\\dir", path="dir"
        )

    def test_error_invalid_mapping_if_more_than_two_parts(self):
        with pytest.raises(ValueError, match="invalid file path mapping"):
            FilePathMapping.parse("./foo:bar:baz")

    @pytest.mark.parametrize("value", ["C:\\", "d:/path/to"])
    def test_error_must_be_unix_path(self, value: str):
        with pytest.raises(ValidationError, match="path must be a Unix file path"):
            FilePathMapping.parse(value)
