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
