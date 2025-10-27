import packaging.version
import pytest

from dstack._internal.utils.version import parse_version


class TestParseVersion:
    @pytest.mark.parametrize("version", ["0.0.0", "0.0.0.dev0", "0.0.0alpha", "latest"])
    def test_latest(self, version: str):
        assert parse_version(version) is None

    def test_release(self):
        assert parse_version("0.19.27") == packaging.version.parse("0.19.27")

    def test_error_invalid_version(self):
        with pytest.raises(ValueError, match=r"Invalid version: 0\.0invalid"):
            parse_version("0.0invalid")
