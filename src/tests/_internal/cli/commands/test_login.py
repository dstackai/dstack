from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pytest import CaptureFixture

from tests._internal.cli.common import run_dstack_cli


class TestLogin:
    def test_login_no_projects(self, capsys: CaptureFixture, tmp_path: Path):
        with (
            patch("dstack._internal.cli.commands.login.webbrowser") as webbrowser_mock,
            patch("dstack._internal.cli.commands.login.APIClient") as APIClientMock,
            patch("dstack._internal.cli.commands.login._LoginServer") as LoginServerMock,
        ):
            webbrowser_mock.open.return_value = True
            APIClientMock.return_value.auth.list_providers.return_value = [
                SimpleNamespace(name="github", enabled=True)
            ]
            APIClientMock.return_value.auth.authorize.return_value = SimpleNamespace(
                authorization_url="http://auth_url"
            )
            APIClientMock.return_value.projects.list.return_value = []
            user = SimpleNamespace(username="me", creds=SimpleNamespace(token="token"))
            LoginServerMock.return_value.get_logged_in_user.return_value = user
            exit_code = run_dstack_cli(
                [
                    "login",
                    "--url",
                    "http://127.0.0.1:31313",
                    "--provider",
                    "github",
                ],
                home_dir=tmp_path,
            )

        assert exit_code == 0
        assert capsys.readouterr().out == (
            "Your browser has been opened to log in with \x1b[1;38;5;78mGithub\x1b[0m:\n\n"
            "http://auth_url\n\n"
            "Logged in as \x1b[1;38;5;78mme\x1b[0m.\n"
            "No projects configured.\n"
        )
