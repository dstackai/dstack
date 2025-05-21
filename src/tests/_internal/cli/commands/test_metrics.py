import pytest

from dstack._internal.cli.commands.metrics import _format_memory


@pytest.mark.parametrize(
    "bytes_value,decimal_places,expected",
    [
        # Test MB values with different decimal places
        (512 * 1024 * 1024, 0, "512MB"),  # exact MB, no decimals
        (512 * 1024 * 1024, 2, "512MB"),  # exact MB, with decimals
        (512.5 * 1024 * 1024, 0, "512MB"),  # decimal MB, no decimals
        (512.5 * 1024 * 1024, 2, "512.5MB"),  # decimal MB, 2 decimals
        (512.5 * 1024 * 1024, 3, "512.5MB"),  # decimal MB, 3 decimals
        (999 * 1024 * 1024, 0, "999MB"),  # just under 1GB, no decimals
        (999 * 1024 * 1024, 2, "999MB"),  # just under 1GB, with decimals
        # Test GB values with different decimal places
        (1.5 * 1024 * 1024 * 1024, 0, "2GB"),  # decimal GB, no decimals
        (1.5 * 1024 * 1024 * 1024, 2, "1.5GB"),  # decimal GB, 2 decimals
        (1.5 * 1024 * 1024 * 1024, 3, "1.5GB"),  # decimal GB, 3 decimals
        (2 * 1024 * 1024 * 1024, 0, "2GB"),  # exact GB, no decimals
        (2 * 1024 * 1024 * 1024, 2, "2GB"),  # exact GB, with decimals
        # Test edge cases
        (0, 0, "0MB"),  # zero bytes, no decimals
        (0, 2, "0MB"),  # zero bytes, with decimals
        (1023 * 1024, 0, "1MB"),  # just under 1MB, no decimals
        (1023 * 1024, 2, "1MB"),  # just under 1MB, with decimals
        (1024 * 1024 * 1024 - 1, 0, "1024MB"),  # just under 1GB, no decimals
        (1024 * 1024 * 1024 - 1, 2, "1024MB"),  # just under 1GB, with decimals
    ],
)
def test_format_memory(bytes_value: int, decimal_places: int, expected: str):
    result = _format_memory(bytes_value, decimal_places)
    assert result == expected
