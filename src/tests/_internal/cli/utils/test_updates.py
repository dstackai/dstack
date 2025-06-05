import pytest

from dstack._internal.cli.utils import updates


@pytest.mark.parametrize(
    "current_version,latest_version,expected",
    [
        ("1.0.0", "1.0.1", True),  # patch update, both releases
        ("1.0.0", "2.0.0", True),  # major update, both releases
        ("1.0.0", "1.0.0", False),  # same version
        ("1.1.0", "1.0.9", False),  # downgrade
        ("1.0.0a1", "1.0.0", True),  # pre-release to release (should show update)
        ("1.0.0", "1.0.0a1", False),  # release to pre-release (should NOT show update)
        ("1.0.0b1", "1.0.0b2", True),  # beta to beta (should show update)
        ("1.0.0rc1", "1.0.0", True),  # rc to release (should show update)
        ("1.0.0", "1.0.0rc1", False),  # release to rc (should NOT show update)
        ("1.0.0a1", "1.0.0b1", True),  # alpha to beta (should show update)
        ("1.0.0b1", "1.0.0rc1", True),  # beta to rc (should show update)
        ("1.0.0rc1", "1.0.1a1", True),  # rc to next alpha (should show update)
    ],
)
def test_is_update_available(current_version, latest_version, expected):
    assert updates.is_update_available(current_version, latest_version) == expected
