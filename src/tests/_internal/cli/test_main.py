import signal
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from unittest.mock import Mock

import pytest
from pytest import CaptureFixture

import dstack._internal.cli.main as main_module
from dstack._internal.compat import IS_WINDOWS
from tests._internal.cli.common import run_dstack_cli


class TestMain:
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

    def test_reraises_keyboard_interrupt(self, monkeypatch: pytest.MonkeyPatch, capsys):
        monkeypatch.setattr(sys, "excepthook", sys.excepthook)
        monkeypatch.setattr(main_module, "check_for_updates", Mock(side_effect=KeyboardInterrupt))

        with pytest.raises(KeyboardInterrupt):
            run_dstack_cli([])

        assert "Interrupted" in capsys.readouterr().err
        assert sys.excepthook is main_module._excepthook_without_keyboard_interrupt

    @pytest.mark.skipif(IS_WINDOWS, reason="Windows has no exit-by-signal status")
    def test_process_exits_via_sigint_without_traceback(self):
        # Spawns a Python process: only the interpreter's own handling of an uncaught exception
        # shows that the CLI exits via SIGINT and that the excepthook hides the traceback.
        code = dedent(
            """
            import sys
            from unittest.mock import patch

            sys.argv = ["dstack"]
            with patch("dstack._internal.cli.main.check_for_updates", side_effect=KeyboardInterrupt):
                from dstack._internal.cli.main import main

                main()
            """
        )

        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

        assert result.returncode == -signal.SIGINT
        assert "Interrupted" in result.stderr
        assert "Traceback" not in result.stderr


class TestExcepthookWithoutKeyboardInterrupt:
    def test_hides_keyboard_interrupt(self, capsys):
        main_module._excepthook_without_keyboard_interrupt(
            KeyboardInterrupt, KeyboardInterrupt(), None
        )

        assert capsys.readouterr().err == ""

    def test_prints_other_exceptions(self, capsys):
        main_module._excepthook_without_keyboard_interrupt(ValueError, ValueError("boom"), None)

        assert "ValueError: boom" in capsys.readouterr().err
