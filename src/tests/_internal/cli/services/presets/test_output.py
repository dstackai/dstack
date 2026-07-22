from datetime import timedelta
from io import StringIO

import pytest
from rich.console import Console
from rich.table import Table
from rich.theme import Theme

from dstack._internal.cli.services.presets import output as output_module
from dstack._internal.cli.services.presets.output import _add_session, _format_number
from tests._internal.cli.preset_factories import get_preset

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

        assert row["STATUS"] == "[bold sea_green3]clauding[/] [secondary](2/3)[/]"
        assert row["BENCHMARK"] == "best trial: con=8 2339 tok/s"
        assert row["GPU"] == "A40:48GB:1"

    def test_shows_zero_progress_without_benchmark(self):
        row = _session_row(
            {"id": "ab12cd34", "status": "running", "max_trials": 3, "trials": {"count": 0}}
        )

        assert row["STATUS"] == "[bold sea_green3]clauding[/] [secondary](0/3)[/]"
        assert row["BENCHMARK"] == ""

    def test_omits_progress_without_trials_data(self):
        row = _session_row({"id": "ab12cd34", "status": "interrupted"})

        assert row["STATUS"] == "[bold gold1]interrupted[/]"

    def test_counts_without_max_trials(self):
        row = _session_row({"id": "ab12cd34", "status": "interrupted", "trials": {"count": 2}})

        assert row["STATUS"] == "[bold gold1]interrupted[/] [secondary](2)[/]"


class TestGroupOrdering:
    def test_sorts_presets_and_sessions_newest_first(self, monkeypatch):
        buffer = StringIO()
        monkeypatch.setattr(
            output_module,
            "console",
            Console(
                file=buffer, width=200, color_system=None, theme=Theme({"secondary": "grey58"})
            ),
        )
        old = get_preset()
        new = old.copy(update={"id": "11aa22bb", "created_at": old.created_at + timedelta(days=2)})
        sessions = [
            {
                "id": "aaaaaaaa",
                "status": "interrupted",
                "model": old.base,
                "created_at": "2026-07-01T00:00:00+00:00",
            },
            {
                "id": "bbbbbbbb",
                "status": "interrupted",
                "model": old.base,
                "created_at": "2026-07-02T00:00:00+00:00",
            },
        ]

        output_module.print_presets([old, new], sessions=sessions)

        text = buffer.getvalue()
        assert text.index("11aa22bb") < text.index(old.id)
        assert text.index(old.id) < text.index("bbbbbbbb") < text.index("aaaaaaaa")


class TestDoneProgress:
    def test_completed_creation_decorates_preset_row_without_extra_session_row(self, monkeypatch):
        buffer = StringIO()
        monkeypatch.setattr(
            output_module,
            "console",
            Console(
                file=buffer, width=200, color_system=None, theme=Theme({"secondary": "grey58"})
            ),
        )
        preset = get_preset()
        sessions = [
            {
                "id": preset.id,
                "status": "success",
                "model": preset.base,
                "max_trials": 4,
                "trials": {"count": 3},
            }
        ]

        output_module.print_presets([preset], sessions=sessions)

        text = buffer.getvalue()
        assert "verified (3/4)" in text
        assert text.count(preset.id) == 1


class TestVerifyingStatus:
    def test_running_session_with_exhausted_trials_shows_verifying(self):
        row = _session_row(
            {"id": "ab12cd34", "status": "running", "max_trials": 2, "trials": {"count": 2}}
        )

        assert row["STATUS"] == "[bold deep_sky_blue1]verifying[/] [secondary](2/2)[/]"

    def test_running_session_with_remaining_trials_stays_clauding(self):
        row = _session_row(
            {"id": "ab12cd34", "status": "running", "max_trials": 2, "trials": {"count": 1}}
        )

        assert row["STATUS"].startswith("[bold sea_green3]clauding[/]")
