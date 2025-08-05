import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest

from dstack._internal.cli.utils.common import _get_cli_log_file


@pytest.fixture
def mock_dstack_dir(tmp_path: Path) -> Generator[Path, None, None]:
    with patch("dstack._internal.cli.utils.common.get_dstack_dir") as mock:
        mock.return_value = tmp_path
        yield tmp_path


class TestGetCliLogFile:
    def test_no_existing_dir(self, mock_dstack_dir: Path):
        log_dir = mock_dstack_dir / "logs" / "cli"
        expected_log_file = log_dir / "latest.log"
        assert not log_dir.exists()

        result = _get_cli_log_file()

        assert log_dir.exists()
        assert result == expected_log_file

    def test_no_rotation_needed_for_today_file(self, mock_dstack_dir: Path):
        log_dir = mock_dstack_dir / "logs" / "cli"
        log_dir.mkdir(parents=True, exist_ok=True)
        latest_log = log_dir / "latest.log"
        latest_log.touch()

        result = _get_cli_log_file()

        assert result == latest_log
        assert latest_log.exists(), "latest.log should not have been renamed"

    @patch("dstack._internal.cli.utils.common.datetime")
    def test_simple_rotation(self, mock_datetime, mock_dstack_dir: Path):
        # Mock "now" to be a specific date
        now = datetime(2023, 10, 27, 10, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now
        # Ensure fromtimestamp still works correctly for the System Under Test
        mock_datetime.fromtimestamp.side_effect = lambda ts, tz: datetime.fromtimestamp(ts, tz)

        log_dir = mock_dstack_dir / "logs" / "cli"
        log_dir.mkdir(parents=True, exist_ok=True)
        latest_log = log_dir / "latest.log"
        latest_log.touch()

        # Set the modification time to yesterday
        yesterday = now - timedelta(days=1)
        mtime = yesterday.timestamp()
        os.utime(latest_log, (mtime, mtime))

        # The expected rotated file name is based on the modification time (yesterday)
        date_str = yesterday.strftime("%Y-%m-%d")
        expected_rotated_log = log_dir / f"{date_str}.log"

        result = _get_cli_log_file()

        assert result == log_dir / "latest.log"
        assert not latest_log.exists(), "The original latest.log should have been renamed"
        assert expected_rotated_log.exists(), "The log file should have been rotated"

    @patch("dstack._internal.cli.utils.common.datetime")
    def test_rotation_with_conflict(self, mock_datetime, mock_dstack_dir: Path):
        now = datetime(2023, 10, 27, 10, 0, 0, tzinfo=timezone.utc)
        yesterday = now - timedelta(days=1)
        mock_datetime.now.return_value = now
        mock_datetime.fromtimestamp.side_effect = lambda ts, tz: datetime.fromtimestamp(ts, tz)

        log_dir = mock_dstack_dir / "logs" / "cli"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create the old 'latest.log' and set its modification time to yesterday
        latest_log = log_dir / "latest.log"
        latest_log.touch()
        mtime = yesterday.timestamp()
        os.utime(latest_log, (mtime, mtime))

        # Create conflicting files that already exist from a previous rotation
        date_str = yesterday.strftime("%Y-%m-%d")
        conflicting_log_1 = log_dir / f"{date_str}.log"
        conflicting_log_1.touch()
        conflicting_log_2 = log_dir / f"{date_str}-1.log"
        conflicting_log_2.touch()

        # We expect the file to be rotated to the next available counter
        expected_rotated_log = log_dir / f"{date_str}-2.log"

        result = _get_cli_log_file()

        assert result == log_dir / "latest.log"
        assert not latest_log.exists(), "The original latest.log should have been renamed"
        assert conflicting_log_1.exists(), "Existing rotated log should be untouched"
        assert conflicting_log_2.exists(), "Existing rotated log with counter should be untouched"
        assert expected_rotated_log.exists(), (
            "The log should have rotated to the next available counter"
        )
