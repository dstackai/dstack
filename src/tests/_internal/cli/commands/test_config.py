from pathlib import Path
from unittest.mock import patch

import yaml
from pytest import CaptureFixture

from tests._internal.cli.common import run_dstack_cli


class TestConfig:
    def test_configures_project(self, capsys: CaptureFixture, tmp_path: Path):
        cli_config_path = tmp_path / ".dstack" / "config.yml"
        with patch("dstack.api.server.APIClient") as APIClientMock:
            api_client_mock = APIClientMock.return_value
            api_client_mock.projects.get
            exit_code = run_dstack_cli(
                [
                    "config",
                    "--url",
                    "http://127.0.0.1:31313",
                    "--project",
                    "project",
                    "--token",
                    "token",
                ],
                home_dir=tmp_path,
            )
            APIClientMock.assert_called_once_with(base_url="http://127.0.0.1:31313", token="token")
        assert exit_code == 0, capsys.readouterr().out
        assert (
            capsys.readouterr().out.replace("\n", "")
            == f"Configuration updated at {cli_config_path}"
        )
        assert yaml.load(cli_config_path.read_text(), yaml.FullLoader) == {
            "projects": [
                {
                    "default": True,
                    "name": "project",
                    "token": "token",
                    "url": "http://127.0.0.1:31313",
                }
            ],
            "repos": [],
        }
