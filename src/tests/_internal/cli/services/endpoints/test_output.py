import pytest

from dstack._internal.cli.services.endpoints.output import _format_number

pytestmark = pytest.mark.windows


class TestFormatNumber:
    def test_large_values_avoid_scientific_notation(self):
        assert _format_number(1723.4) == "1723"
        assert _format_number(999.6) == "1000"

    def test_small_values_keep_three_significant_digits(self):
        assert _format_number(384.8) == "385"
        assert _format_number(15.92) == "15.9"
        assert _format_number(0.99) == "0.99"
