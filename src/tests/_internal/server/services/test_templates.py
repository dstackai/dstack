import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from git import GitCommandError

from dstack._internal.core.models.templates import (
    EnvUITemplateParameter,
    NameUITemplateParameter,
)
from dstack._internal.server.services import templates as templates_service


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the templates cache before each test."""
    templates_service._templates_cache.clear()
    yield
    templates_service._templates_cache.clear()


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
            project = type("Project", (), {"templates_repo": None, "id": "project-id"})()
            result = await templates_service.list_templates(project)
        assert result == []


class TestParseTemplates:
    def test_returns_empty_when_templates_dir_missing(self, tmp_path: Path):
        result = templates_service._parse_templates(tmp_path)
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
        result = templates_service._parse_templates(tmp_path)
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
        result = templates_service._parse_templates(tmp_path)
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
        result = templates_service._parse_templates(tmp_path)
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_skips_non_template_type(self, tmp_path: Path):
        templates_dir = _create_templates_repo(tmp_path)
        _create_template_file(
            templates_dir,
            "other.yml",
            {"type": "something-else", "name": "other", "title": "Other"},
        )
        result = templates_service._parse_templates(tmp_path)
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
        result = templates_service._parse_templates(tmp_path)
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
        result = templates_service._parse_templates(tmp_path)
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
        result = templates_service._parse_templates(tmp_path)
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
        result = templates_service._parse_templates(tmp_path)
        assert len(result) == 2
        assert result[0].name == "a"
        assert result[1].name == "b"


class TestListTemplatesSync:
    def test_returns_empty_if_repo_fetch_fails(self):
        with patch.object(
            templates_service,
            "_fetch_templates_repo",
            side_effect=GitCommandError(["git", "clone"], 128, stderr="not found"),
        ):
            result = templates_service._list_templates_sync(
                "project-key", "https://github.com/dstackai/dstack-sky"
            )
        assert result == []

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
            patch.object(templates_service, "_fetch_templates_repo", return_value=tmp_path),
        ):
            result1 = templates_service._list_templates_sync("project-key", "https://example.com")
            assert len(result1) == 1

            (templates_dir / "test.yml").unlink()

            result2 = templates_service._list_templates_sync("project-key", "https://example.com")
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
            patch.object(templates_service, "_fetch_templates_repo", return_value=tmp_path),
        ):
            result1 = templates_service._list_templates_sync("project-key", "https://example.com")
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

            result2 = templates_service._list_templates_sync("project-key", "https://example.com")
            assert result2[0].name == "updated"

    def test_refreshes_after_cache_ttl_expiration(self, tmp_path: Path):
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

        with patch.object(templates_service, "_fetch_templates_repo", return_value=tmp_path):
            result1 = templates_service._list_templates_sync("project-key", "https://example.com")
            assert result1[0].name == "original"

            _create_template_file(
                templates_dir,
                "test.yml",
                {
                    "type": "template",
                    "name": "updated-after-expire",
                    "title": "Updated",
                    "configuration": {"type": "task"},
                },
            )

            templates_service._templates_cache.expire(
                time=templates_service._templates_cache.timer()
                + templates_service.CACHE_TTL_SECONDS
                + 1
            )

            result2 = templates_service._list_templates_sync("project-key", "https://example.com")
            assert result2[0].name == "updated-after-expire"


class TestInvalidateTemplatesCache:
    def test_removes_cache_entries_for_project_repo_keys(self):
        templates_service._templates_cache.clear()
        project_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        repo1 = "https://example.com/templates-1.git"
        repo2 = "https://example.com/templates-2.git"
        key1 = templates_service._repo_key(project_id=project_id, repo_url=repo1)
        key2 = templates_service._repo_key(project_id=project_id, repo_url=repo2)
        templates_service._templates_cache[(key1, repo1)] = ["a"]
        templates_service._templates_cache[(key2, repo2)] = ["b"]

        templates_service.invalidate_templates_cache(project_id, repo1, repo2)

        assert (key1, repo1) not in templates_service._templates_cache
        assert (key2, repo2) not in templates_service._templates_cache
