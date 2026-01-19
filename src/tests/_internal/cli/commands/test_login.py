from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

from pytest import CaptureFixture

from tests._internal.cli.common import run_dstack_cli


class TestLogin:
    def test_login_no_projects(self, capsys: CaptureFixture, tmp_path: Path):
        with (
            patch("dstack._internal.cli.commands.login.webbrowser") as webbrowser_mock,
            patch("dstack._internal.cli.commands.login.APIClient") as APIClientMock,
            patch("dstack._internal.cli.commands.login._LoginServer") as LoginServerMock,
            patch(
                "dstack._internal.cli.commands.login._normalize_url_or_error"
            ) as _normalize_url_or_error_mock,
        ):
            webbrowser_mock.open.return_value = True
            _normalize_url_or_error_mock.return_value = "http://127.0.0.1:31313"
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
        assert capsys.readouterr().out.replace("\n", "") == (
            "Your browser has been opened to log in with Github:"
            "http://auth_url"
            "Logged in as me."
            "No projects configured. Create your own project via the UI or contact a project manager to add you to the project."
        )

    def test_login_configures_projects(self, capsys: CaptureFixture, tmp_path: Path):
        with (
            patch("dstack._internal.cli.commands.login.webbrowser") as webbrowser_mock,
            patch("dstack._internal.cli.commands.login.APIClient") as APIClientMock,
            patch("dstack._internal.cli.commands.login.ConfigManager") as ConfigManagerMock,
            patch("dstack._internal.cli.commands.login._LoginServer") as LoginServerMock,
            patch(
                "dstack._internal.cli.commands.login._normalize_url_or_error"
            ) as _normalize_url_or_error_mock,
        ):
            _normalize_url_or_error_mock.return_value = "http://127.0.0.1:31313"
            webbrowser_mock.open.return_value = True
            APIClientMock.return_value.auth.list_providers.return_value = [
                SimpleNamespace(name="github", enabled=True)
            ]
            APIClientMock.return_value.auth.authorize.return_value = SimpleNamespace(
                authorization_url="http://auth_url"
            )
            APIClientMock.return_value.projects.list.return_value = [
                SimpleNamespace(project_name="project1"),
                SimpleNamespace(project_name="project2"),
            ]
            APIClientMock.return_value.base_url = "http://127.0.0.1:31313"
            ConfigManagerMock.return_value.get_project_config.return_value = None
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
            ConfigManagerMock.return_value.configure_project.assert_has_calls(
                [
                    call(
                        name="project1",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=True,
                    ),
                    call(
                        name="project2",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=False,
                    ),
                ]
            )
            ConfigManagerMock.return_value.save.assert_called()

        assert exit_code == 0
        assert capsys.readouterr().out.replace("\n", "") == (
            "Your browser has been opened to log in with Github:"
            "http://auth_url"
            "Logged in as me."
            "Configured projects: project1, project2."
            "Set project project1 as default project."
        )
