from pathlib import Path
from unittest.mock import patch

import yaml
from pytest import CaptureFixture

from tests._internal.cli.common import run_dstack_cli


class TestProjectAdd:
    def test_adds_project(self, capsys: CaptureFixture, tmp_path: Path):
        cli_config_path = tmp_path / ".dstack" / "config.yml"
        with patch("dstack.api.server.APIClient") as APIClientMock:
            api_client_mock = APIClientMock.return_value
            exit_code = run_dstack_cli(
                [
                    "project",
                    "add",
                    "--name",
                    "project",
                    "--url",
                    "http://127.0.0.1:31313",
                    "--token",
                    "token",
                    "-y",
                ],
                home_dir=tmp_path,
            )
            APIClientMock.assert_called_once_with(base_url="http://127.0.0.1:31313", token="token")
            api_client_mock.projects.get.assert_called_with("project")
        assert exit_code == 0
        assert yaml.load(cli_config_path.read_text(), yaml.FullLoader) == {
            "projects": [
                {
                    "default": True,
                    "name": "project",
                    "token": "token",
                    "url": "http://127.0.0.1:31313",
                }
            ],
        }
