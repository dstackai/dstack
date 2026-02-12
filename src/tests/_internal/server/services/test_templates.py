from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from dstack._internal.core.models.templates import (
    EnvUITemplateParameter,
    NameUITemplateParameter,
)
from dstack._internal.server.services import templates as templates_service


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the templates cache before each test."""
    templates_service._templates_cache.clear()
    templates_service._repo_path = None
    yield
    templates_service._templates_cache.clear()
    templates_service._repo_path = None


def _create_template_file(templates_dir: Path, filename: str, data: dict) -> Path:
    filepath = templates_dir / filename
    with open(filepath, "w") as f:
        yaml.dump(data, f)
    return filepath


def _create_templates_repo(tmp_path: Path) -> Path:
    """Create a fake templates repo directory with .dstack/templates/."""
    templates_dir = tmp_path / ".dstack" / "templates"
    templates_dir.mkdir(parents=True)
    return templates_dir


class TestListTemplates:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_repo_configured(self):
        with patch.object(templates_service.settings, "SERVER_TEMPLATES_REPO", None):
            result = await templates_service.list_templates()
        assert result == []


class TestParseTemplates:
    def test_returns_empty_when_repo_path_is_none(self):
        result = templates_service._parse_templates()
        assert result == []

    def test_returns_empty_when_templates_dir_missing(self, tmp_path: Path):
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert result == []

    def test_parses_valid_template(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "test.yml",
            {
                "type": "ui-template",
                "id": "test-template",
                "title": "Test Template",
                "parameters": [{"type": "name"}],
                "template": {"type": "dev-environment"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        assert result[0].id == "test-template"
        assert isinstance(result[0].parameters[0], NameUITemplateParameter)

    def test_parses_template_with_env_parameter(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "test.yml",
            {
                "type": "ui-template",
                "id": "test",
                "title": "Test",
                "parameters": [
                    {"type": "env", "title": "Password", "name": "PASSWORD", "value": "secret"}
                ],
                "template": {"type": "service"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        param = result[0].parameters[0]
        assert isinstance(param, EnvUITemplateParameter)
        assert param.title == "Password"
        assert param.name == "PASSWORD"
        assert param.value == "secret"

    def test_skips_non_yaml_files(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "valid.yml",
            {
                "type": "ui-template",
                "id": "valid",
                "title": "Valid",
                "template": {"type": "task"},
            },
        )
        (templates_dir / "readme.txt").write_text("not a template")
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        assert result[0].id == "valid"

    def test_skips_non_ui_template_type(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "other.yml",
            {"type": "something-else", "id": "other", "title": "Other"},
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert result == []

    def test_skips_invalid_yaml(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        (templates_dir / "bad.yml").write_text(": invalid: yaml: [")
        _create_template_file(
            templates_dir,
            "good.yml",
            {
                "type": "ui-template",
                "id": "good",
                "title": "Good",
                "template": {"type": "task"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        assert result[0].id == "good"

    def test_skips_template_with_unknown_parameter_type(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "bad_param.yml",
            {
                "type": "ui-template",
                "id": "bad-param",
                "title": "Bad Param",
                "parameters": [{"type": "unknown_type"}],
                "template": {"type": "task"},
            },
        )
        _create_template_file(
            templates_dir,
            "good.yml",
            {
                "type": "ui-template",
                "id": "good",
                "title": "Good",
                "template": {"type": "task"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        assert result[0].id == "good"

    def test_parses_yaml_extension(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "test.yaml",
            {
                "type": "ui-template",
                "id": "yaml-ext",
                "title": "YAML Extension",
                "template": {"type": "task"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        assert result[0].id == "yaml-ext"

    def test_returns_templates_sorted_by_filename(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "b.yml",
            {
                "type": "ui-template",
                "id": "b",
                "title": "B",
                "template": {"type": "task"},
            },
        )
        _create_template_file(
            templates_dir,
            "a.yml",
            {
                "type": "ui-template",
                "id": "a",
                "title": "A",
                "template": {"type": "task"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 2
        assert result[0].id == "a"
        assert result[1].id == "b"


class TestListTemplatesSync:
    def test_caches_result(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "test.yml",
            {
                "type": "ui-template",
                "id": "cached",
                "title": "Cached",
                "template": {"type": "task"},
            },
        )

        with (
            patch.object(
                templates_service.settings, "SERVER_TEMPLATES_REPO", "https://example.com"
            ),
            patch.object(templates_service, "_fetch_templates_repo"),
        ):
            templates_service._repo_path = tmp_path
            # First call populates cache
            result1 = templates_service._list_templates_sync()
            assert len(result1) == 1

            # Remove the file
            (templates_dir / "test.yml").unlink()

            # Second call returns cached result
            result2 = templates_service._list_templates_sync()
            assert len(result2) == 1
            assert result2[0].id == "cached"

    def test_refreshes_after_cache_clear(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "test.yml",
            {
                "type": "ui-template",
                "id": "original",
                "title": "Original",
                "template": {"type": "task"},
            },
        )

        with (
            patch.object(
                templates_service.settings, "SERVER_TEMPLATES_REPO", "https://example.com"
            ),
            patch.object(templates_service, "_fetch_templates_repo"),
        ):
            templates_service._repo_path = tmp_path
            # First call
            result1 = templates_service._list_templates_sync()
            assert result1[0].id == "original"

            # Update the file and clear cache
            _create_template_file(
                templates_dir,
                "test.yml",
                {
                    "type": "ui-template",
                    "id": "updated",
                    "title": "Updated",
                    "template": {"type": "task"},
                },
            )
            templates_service._templates_cache.clear()

            # Next call refreshes
            result2 = templates_service._list_templates_sync()
            assert result2[0].id == "updated"
