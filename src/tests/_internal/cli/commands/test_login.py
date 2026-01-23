from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

from pytest import CaptureFixture

from tests._internal.cli.common import run_dstack_cli


class TestLogin:
    @staticmethod
    def _setup_auth_mocks(api_client_mock, login_server_mock, user_token="token"):
        """Set up common authentication mocks."""
        api_client_mock.return_value.auth.list_providers.return_value = [
            SimpleNamespace(name="github", enabled=True)
        ]
        api_client_mock.return_value.auth.authorize.return_value = SimpleNamespace(
            authorization_url="http://auth_url"
        )
        user = SimpleNamespace(username="me", creds=SimpleNamespace(token=user_token))
        login_server_mock.return_value.get_logged_in_user.return_value = user
        return user

    @staticmethod
    def _setup_config_manager_with_state_tracking(
        config_manager_mock, tmp_path: Path, project_configs: list[SimpleNamespace]
    ):
        """Set up ConfigManager mock with state tracking via side effects."""
        config_manager_mock.return_value.config_filepath = tmp_path / "config.yml"
        config_manager_mock.return_value.list_project_configs.return_value = project_configs

        def configure_project_side_effect(name, url, token, default):
            for pc in project_configs:
                if pc.name == name:
                    pc.url = url
                    pc.token = token
                    if default:
                        for p in project_configs:
                            p.default = False
                    pc.default = default or pc.default
                    return

        def get_project_config_side_effect(name=None):
            if name is None:
                for pc in project_configs:
                    if pc.default:
                        return pc
                return None
            for pc in project_configs:
                if pc.name == name:
                    return pc
            return None

        config_manager_mock.return_value.configure_project.side_effect = (
            configure_project_side_effect
        )
        config_manager_mock.return_value.get_project_config.side_effect = (
            get_project_config_side_effect
        )

    def test_login_no_projects(self, capsys: CaptureFixture, tmp_path: Path):
        with (
            patch("dstack._internal.cli.commands.login.webbrowser") as webbrowser_mock,
            patch("dstack._internal.cli.commands.login.APIClient") as api_client_mock,
            patch("dstack._internal.cli.commands.login._LoginServer") as login_server_mock,
            patch(
                "dstack._internal.cli.commands.login._normalize_url_or_error"
            ) as normalize_url_mock,
        ):
            webbrowser_mock.open.return_value = True
            normalize_url_mock.return_value = "http://127.0.0.1:31313"
            self._setup_auth_mocks(api_client_mock, login_server_mock)
            api_client_mock.return_value.projects.list.return_value = []

            exit_code = run_dstack_cli(
                ["login", "--url", "http://127.0.0.1:31313", "--provider", "github"],
                home_dir=tmp_path,
            )

        assert exit_code == 0
        assert capsys.readouterr().out.replace("\n", "") == (
            "Your browser has been opened to log in with Github:"
            "http://auth_url"
            "Logged in as me"
            "No projects configured. Create your own project via the UI or contact a project manager to add you to the project."
        )

    def test_login_configures_projects(self, capsys: CaptureFixture, tmp_path: Path):
        with (
            patch("dstack._internal.cli.commands.login.webbrowser") as webbrowser_mock,
            patch("dstack._internal.cli.commands.login.APIClient") as api_client_mock,
            patch("dstack._internal.cli.commands.login.ConfigManager") as config_manager_mock,
            patch("dstack._internal.cli.commands.login._LoginServer") as login_server_mock,
            patch(
                "dstack._internal.cli.commands.login._normalize_url_or_error"
            ) as normalize_url_mock,
        ):
            webbrowser_mock.open.return_value = True
            normalize_url_mock.return_value = "http://127.0.0.1:31313"
            user = self._setup_auth_mocks(api_client_mock, login_server_mock)
            api_client_mock.return_value.projects.list.return_value = [
                SimpleNamespace(project_name="project1"),
                SimpleNamespace(project_name="project2"),
            ]
            api_client_mock.return_value.base_url = "http://127.0.0.1:31313"

            project_configs = [
                SimpleNamespace(
                    name="project1", url="http://127.0.0.1:31313", token="token", default=False
                ),
                SimpleNamespace(
                    name="project2", url="http://127.0.0.1:31313", token="token", default=False
                ),
            ]
            config_manager_mock.return_value.get_project_config.return_value = None
            self._setup_config_manager_with_state_tracking(
                config_manager_mock, tmp_path, project_configs
            )

            exit_code = run_dstack_cli(
                ["login", "--url", "http://127.0.0.1:31313", "--provider", "github"],
                home_dir=tmp_path,
            )

            config_manager_mock.return_value.configure_project.assert_has_calls(
                [
                    call(
                        name="project1",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=False,
                    ),
                    call(
                        name="project2",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=False,
                    ),
                    call(
                        name="project1", url="http://127.0.0.1:31313", token="token", default=True
                    ),
                ]
            )
            config_manager_mock.return_value.save.assert_called()
            final_default = config_manager_mock.return_value.get_project_config()
            assert final_default is not None
            assert final_default.name == "project1"

        assert exit_code == 0
        assert capsys.readouterr().out.replace("\n", "") == (
            "Your browser has been opened to log in with Github:"
            "http://auth_url"
            "Logged in as me"
            f"Added project1, project2 projects at {tmp_path / 'config.yml'}"
            f"Set project1 project as default at {tmp_path / 'config.yml'}"
        )

    def test_login_configures_projects_yes_sets_first_project_default(
        self, capsys: CaptureFixture, tmp_path: Path
    ):
        with (
            patch("dstack._internal.cli.commands.login.webbrowser") as webbrowser_mock,
            patch("dstack._internal.cli.commands.login.APIClient") as api_client_mock,
            patch("dstack._internal.cli.commands.login.ConfigManager") as config_manager_mock,
            patch("dstack._internal.cli.commands.login._LoginServer") as login_server_mock,
            patch(
                "dstack._internal.cli.commands.login._normalize_url_or_error"
            ) as normalize_url_mock,
        ):
            webbrowser_mock.open.return_value = True
            normalize_url_mock.return_value = "http://127.0.0.1:31313"
            user = self._setup_auth_mocks(api_client_mock, login_server_mock)
            api_client_mock.return_value.projects.list.return_value = [
                SimpleNamespace(project_name="project1"),
                SimpleNamespace(project_name="project2"),
            ]
            api_client_mock.return_value.base_url = "http://127.0.0.1:31313"

            project_configs = [
                SimpleNamespace(
                    name="project1", url="http://127.0.0.1:31313", token="token", default=False
                ),
                SimpleNamespace(
                    name="project2", url="http://127.0.0.1:31313", token="token", default=True
                ),
            ]
            self._setup_config_manager_with_state_tracking(
                config_manager_mock, tmp_path, project_configs
            )

            exit_code = run_dstack_cli(
                ["login", "--url", "http://127.0.0.1:31313", "--provider", "github", "--yes"],
                home_dir=tmp_path,
            )

            config_manager_mock.return_value.configure_project.assert_has_calls(
                [
                    call(
                        name="project1",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=False,
                    ),
                    call(
                        name="project2",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=False,
                    ),
                    call(
                        name="project1", url="http://127.0.0.1:31313", token="token", default=True
                    ),
                ]
            )
            final_default = config_manager_mock.return_value.get_project_config()
            assert final_default is not None
            assert final_default.name == "project1"

        assert exit_code == 0
        assert capsys.readouterr().out.replace("\n", "") == (
            "Your browser has been opened to log in with Github:"
            "http://auth_url"
            "Logged in as me"
            f"Added project1, project2 projects at {tmp_path / 'config.yml'}"
            f"Set project1 project as default at {tmp_path / 'config.yml'}"
        )

    def test_login_configures_projects_no_does_not_change_default(
        self, capsys: CaptureFixture, tmp_path: Path
    ):
        with (
            patch("dstack._internal.cli.commands.login.webbrowser") as webbrowser_mock,
            patch("dstack._internal.cli.commands.login.APIClient") as api_client_mock,
            patch("dstack._internal.cli.commands.login.ConfigManager") as config_manager_mock,
            patch("dstack._internal.cli.commands.login._LoginServer") as login_server_mock,
            patch(
                "dstack._internal.cli.commands.login._normalize_url_or_error"
            ) as normalize_url_mock,
        ):
            webbrowser_mock.open.return_value = True
            normalize_url_mock.return_value = "http://127.0.0.1:31313"
            user = self._setup_auth_mocks(api_client_mock, login_server_mock)
            api_client_mock.return_value.projects.list.return_value = [
                SimpleNamespace(project_name="project1"),
                SimpleNamespace(project_name="project2"),
            ]
            api_client_mock.return_value.base_url = "http://127.0.0.1:31313"

            project_configs = [
                SimpleNamespace(
                    name="project1", url="http://127.0.0.1:31313", token="token", default=False
                ),
                SimpleNamespace(
                    name="project2", url="http://127.0.0.1:31313", token="token", default=True
                ),
            ]
            self._setup_config_manager_with_state_tracking(
                config_manager_mock, tmp_path, project_configs
            )

            exit_code = run_dstack_cli(
                ["login", "--url", "http://127.0.0.1:31313", "--provider", "github", "--no"],
                home_dir=tmp_path,
            )

            config_manager_mock.return_value.configure_project.assert_has_calls(
                [
                    call(
                        name="project1",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=False,
                    ),
                    call(
                        name="project2",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=False,
                    ),
                ]
            )
            assert (
                call(name="project1", url="http://127.0.0.1:31313", token="token", default=True)
                not in config_manager_mock.return_value.configure_project.mock_calls
            )
            final_default = config_manager_mock.return_value.get_project_config()
            assert final_default is not None
            assert final_default.name == "project2"

        assert exit_code == 0
        assert capsys.readouterr().out.replace("\n", "") == (
            "Your browser has been opened to log in with Github:"
            "http://auth_url"
            "Logged in as me"
            f"Added project1, project2 projects at {tmp_path / 'config.yml'}"
        )

    def test_login_single_project_auto_default(self, capsys: CaptureFixture, tmp_path: Path):
        with (
            patch("dstack._internal.cli.commands.login.webbrowser") as webbrowser_mock,
            patch("dstack._internal.cli.commands.login.APIClient") as api_client_mock,
            patch("dstack._internal.cli.commands.login.ConfigManager") as config_manager_mock,
            patch("dstack._internal.cli.commands.login._LoginServer") as login_server_mock,
            patch(
                "dstack._internal.cli.commands.login._normalize_url_or_error"
            ) as normalize_url_mock,
        ):
            webbrowser_mock.open.return_value = True
            normalize_url_mock.return_value = "http://127.0.0.1:31313"
            user = self._setup_auth_mocks(api_client_mock, login_server_mock)
            api_client_mock.return_value.projects.list.return_value = [
                SimpleNamespace(project_name="project1"),
            ]
            api_client_mock.return_value.base_url = "http://127.0.0.1:31313"

            project_configs = [
                SimpleNamespace(
                    name="project1", url="http://127.0.0.1:31313", token="token", default=False
                ),
            ]
            config_manager_mock.return_value.get_project_config.return_value = None
            self._setup_config_manager_with_state_tracking(
                config_manager_mock, tmp_path, project_configs
            )

            exit_code = run_dstack_cli(
                ["login", "--url", "http://127.0.0.1:31313", "--provider", "github"],
                home_dir=tmp_path,
            )

            config_manager_mock.return_value.configure_project.assert_has_calls(
                [
                    call(
                        name="project1",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=False,
                    ),
                    call(
                        name="project1", url="http://127.0.0.1:31313", token="token", default=True
                    ),
                ]
            )
            final_default = config_manager_mock.return_value.get_project_config()
            assert final_default is not None
            assert final_default.name == "project1"

        assert exit_code == 0
        assert capsys.readouterr().out.replace("\n", "") == (
            "Your browser has been opened to log in with Github:"
            "http://auth_url"
            "Logged in as me"
            f"Added project1 project at {tmp_path / 'config.yml'}"
            f"Set project1 project as default at {tmp_path / 'config.yml'}"
        )

    def test_login_interactive_prompts_for_default_project(
        self, capsys: CaptureFixture, tmp_path: Path
    ):
        with (
            patch("dstack._internal.cli.commands.login.webbrowser") as webbrowser_mock,
            patch("dstack._internal.cli.commands.login.APIClient") as api_client_mock,
            patch("dstack._internal.cli.commands.login.ConfigManager") as config_manager_mock,
            patch("dstack._internal.cli.commands.login._LoginServer") as login_server_mock,
            patch(
                "dstack._internal.cli.commands.login._normalize_url_or_error"
            ) as normalize_url_mock,
            patch(
                "dstack._internal.cli.commands.login.select_default_project"
            ) as select_default_project_mock,
            patch("dstack._internal.cli.commands.login.is_project_menu_supported", True),
        ):
            webbrowser_mock.open.return_value = True
            normalize_url_mock.return_value = "http://127.0.0.1:31313"
            user = self._setup_auth_mocks(api_client_mock, login_server_mock)
            api_client_mock.return_value.projects.list.return_value = [
                SimpleNamespace(project_name="project1"),
                SimpleNamespace(project_name="project2"),
            ]
            api_client_mock.return_value.base_url = "http://127.0.0.1:31313"

            project_configs = [
                SimpleNamespace(
                    name="project1", url="http://127.0.0.1:31313", token="token", default=False
                ),
                SimpleNamespace(
                    name="project2", url="http://127.0.0.1:31313", token="token", default=False
                ),
            ]
            config_manager_mock.return_value.get_project_config.return_value = None
            self._setup_config_manager_with_state_tracking(
                config_manager_mock, tmp_path, project_configs
            )
            select_default_project_mock.return_value = project_configs[1]

            exit_code = run_dstack_cli(
                ["login", "--url", "http://127.0.0.1:31313", "--provider", "github"],
                home_dir=tmp_path,
            )

            select_default_project_mock.assert_called_once()
            config_manager_mock.return_value.configure_project.assert_has_calls(
                [
                    call(
                        name="project1",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=False,
                    ),
                    call(
                        name="project2",
                        url="http://127.0.0.1:31313",
                        token=user.creds.token,
                        default=False,
                    ),
                    call(
                        name="project2", url="http://127.0.0.1:31313", token="token", default=True
                    ),
                ]
            )
            final_default = config_manager_mock.return_value.get_project_config()
            assert final_default is not None
            assert final_default.name == "project2"

        assert exit_code == 0
        assert capsys.readouterr().out.replace("\n", "") == (
            "Your browser has been opened to log in with Github:"
            "http://auth_url"
            "Logged in as me"
            f"Added project1, project2 projects at {tmp_path / 'config.yml'}"
        )
