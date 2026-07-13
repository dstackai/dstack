from unittest.mock import patch

from dstack._internal.core.models.config import ProjectConfig
from dstack._internal.core.services.api_client import get_api_client


class TestGetAPIClient:
    def test_uses_complete_environment_config(self, monkeypatch):
        monkeypatch.setenv("DSTACK_SERVER_URL", "http+unix://%2Frun%2Fdstack%2Fserver.sock")
        monkeypatch.setenv("DSTACK_PROJECT", "main")
        monkeypatch.setenv("DSTACK_TOKEN", "token")

        with patch("dstack._internal.core.services.api_client.configs.ConfigManager") as manager:
            client, project_name = get_api_client()

        manager.assert_not_called()
        assert client.base_url == "http+unix://%2Frun%2Fdstack%2Fserver.sock"
        assert project_name == "main"

    def test_incomplete_environment_config_uses_config_file(self, monkeypatch):
        monkeypatch.setenv("DSTACK_SERVER_URL", "http+unix://%2Frun%2Fdstack%2Fserver.sock")
        monkeypatch.setenv("DSTACK_PROJECT", "environment-project")
        monkeypatch.delenv("DSTACK_TOKEN", raising=False)
        project = ProjectConfig(
            name="configured-project",
            url="https://server.example.com",
            token="configured-token",
            default=True,
        )

        with patch("dstack._internal.core.services.api_client.configs.ConfigManager") as manager:
            manager.return_value.get_project_config.return_value = project
            client, project_name = get_api_client()

        assert client.base_url == "https://server.example.com"
        assert project_name == "configured-project"

    def test_token_alone_overrides_configured_token(self, monkeypatch):
        monkeypatch.delenv("DSTACK_SERVER_URL", raising=False)
        monkeypatch.delenv("DSTACK_PROJECT", raising=False)
        monkeypatch.setenv("DSTACK_TOKEN", "environment-token")
        project = ProjectConfig(
            name="configured-project",
            url="https://server.example.com",
            token="configured-token",
            default=True,
        )

        with patch("dstack._internal.core.services.api_client.configs.ConfigManager") as manager:
            manager.return_value.get_project_config.return_value = project
            client, project_name = get_api_client()

        assert client.base_url == "https://server.example.com"
        assert client._s.headers["Authorization"] == "Bearer environment-token"
        assert project_name == "configured-project"
