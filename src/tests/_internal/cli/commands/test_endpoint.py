from pytest import CaptureFixture

from tests._internal.cli.common import run_dstack_cli


class TestEndpointCommand:
    def test_create_help(self, capsys: CaptureFixture):
        exit_code = run_dstack_cli(["endpoint", "create", "--help"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "--model" in output
        assert "--gpu" in output
        assert "--backend" in output

    def test_requires_harness_api_key(self, capsys: CaptureFixture, monkeypatch):
        monkeypatch.delenv("DSTACK_HARNESS_API_KEY", raising=False)
        exit_code = run_dstack_cli(
            ["endpoint", "create", "--model", "meta-llama/Meta-Llama-3.1-8B-Instruct", "--dry-run"]
        )
        assert exit_code == 1
        assert "DSTACK_HARNESS_API_KEY" in capsys.readouterr().out
