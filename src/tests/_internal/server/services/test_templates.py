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
                "type": "template",
                "name": "test-template",
                "title": "Test Template",
                "parameters": [{"type": "name"}],
                "configuration": {"type": "dev-environment"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        assert result[0].name == "test-template"
        assert isinstance(result[0].parameters[0], NameUITemplateParameter)

    def test_parses_template_with_env_parameter(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "test.yml",
            {
                "type": "template",
                "name": "test",
                "title": "Test",
                "parameters": [
                    {"type": "env", "title": "Password", "name": "PASSWORD", "value": "secret"}
                ],
                "configuration": {"type": "service"},
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
                "type": "template",
                "name": "valid",
                "title": "Valid",
                "configuration": {"type": "task"},
            },
        )
        (templates_dir / "readme.txt").write_text("not a template")
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_skips_non_template_type(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "other.yml",
            {"type": "something-else", "name": "other", "title": "Other"},
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
                "type": "template",
                "name": "good",
                "title": "Good",
                "configuration": {"type": "task"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        assert result[0].name == "good"

    def test_skips_template_with_unknown_parameter_type(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "bad_param.yml",
            {
                "type": "template",
                "name": "bad-param",
                "title": "Bad Param",
                "parameters": [{"type": "unknown_type"}],
                "configuration": {"type": "task"},
            },
        )
        _create_template_file(
            templates_dir,
            "good.yml",
            {
                "type": "template",
                "name": "good",
                "title": "Good",
                "configuration": {"type": "task"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        assert result[0].name == "good"

    def test_parses_yaml_extension(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "test.yaml",
            {
                "type": "template",
                "name": "yaml-ext",
                "title": "YAML Extension",
                "configuration": {"type": "task"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 1
        assert result[0].name == "yaml-ext"

    def test_returns_templates_sorted_by_filename(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "b.yml",
            {
                "type": "template",
                "name": "b",
                "title": "B",
                "configuration": {"type": "task"},
            },
        )
        _create_template_file(
            templates_dir,
            "a.yml",
            {
                "type": "template",
                "name": "a",
                "title": "A",
                "configuration": {"type": "task"},
            },
        )
        templates_service._repo_path = tmp_path
        result = templates_service._parse_templates()
        assert len(result) == 2
        assert result[0].name == "a"
        assert result[1].name == "b"


class TestListTemplatesSync:
    def test_caches_result(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "test.yml",
            {
                "type": "template",
                "name": "cached",
                "title": "Cached",
                "configuration": {"type": "task"},
            },
        )

        with (
            patch.object(
                templates_service.settings, "SERVER_TEMPLATES_REPO", "https://example.com"
            ),
            patch.object(templates_service, "_fetch_templates_repo"),
        ):
            templates_service._repo_path = tmp_path
            result1 = templates_service._list_templates_sync()
            assert len(result1) == 1

            (templates_dir / "test.yml").unlink()

            result2 = templates_service._list_templates_sync()
            assert len(result2) == 1
            assert result2[0].name == "cached"

    def test_refreshes_after_cache_clear(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "test.yml",
            {
                "type": "template",
                "name": "original",
                "title": "Original",
                "configuration": {"type": "task"},
            },
        )

        with (
            patch.object(
                templates_service.settings, "SERVER_TEMPLATES_REPO", "https://example.com"
            ),
            patch.object(templates_service, "_fetch_templates_repo"),
        ):
            templates_service._repo_path = tmp_path
            result1 = templates_service._list_templates_sync()
            assert result1[0].name == "original"

            _create_template_file(
                templates_dir,
                "test.yml",
                {
                    "type": "template",
                    "name": "updated",
                    "title": "Updated",
                    "configuration": {"type": "task"},
                },
            )
            templates_service._templates_cache.clear()

            result2 = templates_service._list_templates_sync()
            assert result2[0].name == "updated"
