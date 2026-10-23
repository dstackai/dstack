from pathlib import Path

from pytest import CaptureFixture

from tests._internal.cli.common import run_dstack_cli


class TestDstack:
    def test_prints_help_and_exists_with_0_exit_code(self, capsys: CaptureFixture):
        exit_code = run_dstack_cli([])
        assert exit_code == 0
        assert capsys.readouterr().out.startswith("Usage: dstack [-h] [-v] COMMAND ...")

    def test_prints_errors_to_stderr(self, tmp_path: Path, capsys: CaptureFixture):
        exit_code = run_dstack_cli(["ps", "--nonsense"], home_dir=tmp_path)
        assert exit_code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Unrecognized arguments: --nonsense" in captured.err
