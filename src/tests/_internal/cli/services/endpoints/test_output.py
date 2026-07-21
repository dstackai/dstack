import pytest
from rich.table import Table

from dstack._internal.cli.services.endpoints.output import _add_session, _format_number

pytestmark = pytest.mark.windows


class TestFormatNumber:
    def test_large_values_avoid_scientific_notation(self):
        assert _format_number(1723.4) == "1723"
        assert _format_number(999.6) == "1000"

    def test_small_values_keep_three_significant_digits(self):
        assert _format_number(384.8) == "385"
        assert _format_number(15.92) == "15.9"
        assert _format_number(0.99) == "0.99"


def _session_row(session: dict) -> dict:
    table = Table(box=None)
    for column in ("BASE", "ID", "GPU", "BENCHMARK", "STATUS", "SUBMITTED"):
        table.add_column(column)
    _add_session(table, session)
    return {
        column.header: "".join(str(cell) for cell in column._cells) for column in table.columns
    }


class TestSessionRow:
    def test_shows_progress_after_status_and_best_benchmark(self):
        row = _session_row(
            {
                "id": "c7e18d52",
                "status": "running",
                "max_trials": 3,
                "trials": {
                    "count": 2,
                    "best": {"tok_s": 2339.0, "concurrency": 8, "gpu": "A40:48GB:1"},
                },
            }
        )

        assert row["STATUS"] == "[bold deep_sky_blue1]clauding[/] (2/3)"
        assert row["BENCHMARK"] == "best trial: con=8 2339 tok/s"
        assert row["GPU"] == "A40:48GB:1"

    def test_shows_zero_progress_without_benchmark(self):
        row = _session_row(
            {"id": "ab12cd34", "status": "running", "max_trials": 3, "trials": {"count": 0}}
        )

        assert row["STATUS"] == "[bold deep_sky_blue1]clauding[/] (0/3)"
        assert row["BENCHMARK"] == ""

    def test_omits_progress_without_trials_data(self):
        row = _session_row({"id": "ab12cd34", "status": "interrupted"})

        assert row["STATUS"] == "[bold gold1]interrupted[/]"

    def test_counts_without_max_trials(self):
        row = _session_row({"id": "ab12cd34", "status": "interrupted", "trials": {"count": 2}})

        assert row["STATUS"] == "[bold gold1]interrupted[/] (2)"
