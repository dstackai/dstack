import pytest
from pydantic import ValidationError

from dstack._internal.core.models.templates import (
    EnvUITemplateParameter,
    IDEUITemplateParameter,
    NameUITemplateParameter,
    PythonOrDockerUITemplateParameter,
    RepoUITemplateParameter,
    ResourcesUITemplateParameter,
    UITemplate,
    WorkingDirUITemplateParameter,
)


class TestUITemplateParameter:
    def test_parses_name_parameter(self):
        data = {"type": "name"}
        template = UITemplate.parse_obj(
            {"type": "ui-template", "id": "t", "title": "T", "parameters": [data], "template": {}}
        )
        assert len(template.parameters) == 1
        assert isinstance(template.parameters[0], NameUITemplateParameter)

    def test_parses_ide_parameter(self):
        data = {"type": "ide"}
        template = UITemplate.parse_obj(
            {"type": "ui-template", "id": "t", "title": "T", "parameters": [data], "template": {}}
        )
        assert isinstance(template.parameters[0], IDEUITemplateParameter)

    def test_parses_resources_parameter(self):
        data = {"type": "resources"}
        template = UITemplate.parse_obj(
            {"type": "ui-template", "id": "t", "title": "T", "parameters": [data], "template": {}}
        )
        assert isinstance(template.parameters[0], ResourcesUITemplateParameter)

    def test_parses_python_or_docker_parameter(self):
        data = {"type": "python_or_docker"}
        template = UITemplate.parse_obj(
            {"type": "ui-template", "id": "t", "title": "T", "parameters": [data], "template": {}}
        )
        assert isinstance(template.parameters[0], PythonOrDockerUITemplateParameter)

    def test_parses_repo_parameter(self):
        data = {"type": "repo"}
        template = UITemplate.parse_obj(
            {"type": "ui-template", "id": "t", "title": "T", "parameters": [data], "template": {}}
        )
        assert isinstance(template.parameters[0], RepoUITemplateParameter)

    def test_parses_working_dir_parameter(self):
        data = {"type": "working_dir"}
        template = UITemplate.parse_obj(
            {"type": "ui-template", "id": "t", "title": "T", "parameters": [data], "template": {}}
        )
        assert isinstance(template.parameters[0], WorkingDirUITemplateParameter)

    def test_parses_env_parameter_with_all_fields(self):
        data = {
            "type": "env",
            "title": "Password",
            "name": "PASSWORD",
            "value": "$random-password",
        }
        template = UITemplate.parse_obj(
            {"type": "ui-template", "id": "t", "title": "T", "parameters": [data], "template": {}}
        )
        param = template.parameters[0]
        assert isinstance(param, EnvUITemplateParameter)
        assert param.title == "Password"
        assert param.name == "PASSWORD"
        assert param.value == "$random-password"

    def test_parses_env_parameter_with_no_optional_fields(self):
        data = {"type": "env"}
        template = UITemplate.parse_obj(
            {"type": "ui-template", "id": "t", "title": "T", "parameters": [data], "template": {}}
        )
        param = template.parameters[0]
        assert isinstance(param, EnvUITemplateParameter)
        assert param.title is None
        assert param.name is None
        assert param.value is None

    def test_rejects_unknown_parameter_type(self):
        data = {"type": "unknown_type"}
        with pytest.raises(ValidationError):
            UITemplate.parse_obj(
                {
                    "type": "ui-template",
                    "id": "t",
                    "title": "T",
                    "parameters": [data],
                    "template": {},
                }
            )


class TestUITemplate:
    def test_parses_desktop_ide_template(self):
        data = {
            "type": "ui-template",
            "id": "desktop-ide",
            "title": "Desktop IDE",
            "parameters": [
                {"type": "name"},
                {"type": "ide"},
                {"type": "resources"},
                {"type": "python_or_docker"},
                {"type": "repo"},
                {"type": "working_dir"},
            ],
            "template": {"type": "dev-environment"},
        }
        template = UITemplate.parse_obj(data)
        assert template.id == "desktop-ide"
        assert template.title == "Desktop IDE"
        assert len(template.parameters) == 6
        assert template.template == {"type": "dev-environment"}

    def test_parses_web_based_ide_template(self):
        data = {
            "type": "ui-template",
            "id": "web-based-ide",
            "title": "Web-based IDE",
            "parameters": [
                {"type": "name"},
                {"type": "resources"},
                {"type": "python_or_docker"},
                {"type": "repo"},
                {"type": "working_dir"},
                {
                    "type": "env",
                    "title": "Password",
                    "name": "PASSWORD",
                    "value": "$random-password",
                },
            ],
            "template": {
                "type": "service",
                "auth": False,
                "https": False,
                "env": ["BIND_ADDR=0.0.0.0:8080"],
                "commands": ["echo hello"],
                "port": 8080,
                "probes": [{"type": "http", "url": "/healthz"}],
            },
        }
        template = UITemplate.parse_obj(data)
        assert template.id == "web-based-ide"
        assert template.title == "Web-based IDE"
        assert len(template.parameters) == 6
        assert isinstance(template.parameters[5], EnvUITemplateParameter)
        assert template.template["type"] == "service"
        assert template.template["port"] == 8080

    def test_rejects_wrong_type(self):
        with pytest.raises(ValidationError):
            UITemplate.parse_obj(
                {
                    "type": "not-a-template",
                    "id": "t",
                    "title": "T",
                    "template": {},
                }
            )

    def test_rejects_missing_template(self):
        with pytest.raises(ValidationError):
            UITemplate.parse_obj(
                {
                    "type": "ui-template",
                    "id": "t",
                    "title": "T",
                }
            )

    def test_rejects_missing_id(self):
        with pytest.raises(ValidationError):
            UITemplate.parse_obj(
                {
                    "type": "ui-template",
                    "title": "T",
                    "template": {},
                }
            )

    def test_empty_parameters_default(self):
        template = UITemplate.parse_obj(
            {
                "type": "ui-template",
                "id": "t",
                "title": "T",
                "template": {"type": "task"},
            }
        )
        assert template.parameters == []
