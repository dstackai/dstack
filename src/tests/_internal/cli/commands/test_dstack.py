from pytest import CaptureFixture

from tests._internal.cli.common import run_dstack_cli


class TestDstack:
    def test_prints_help_and_exists_with_0_exit_code(self, capsys: CaptureFixture):
        exit_code = run_dstack_cli([])
        assert exit_code == 0
        assert capsys.readouterr().out.startswith("Usage: dstack [-h] [-v] COMMAND ...")
