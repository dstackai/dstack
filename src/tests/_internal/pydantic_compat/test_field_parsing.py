"""Focused parity tests for user-facing fields with custom parsing or normalization."""

import json
from typing import Any

import pytest
import yaml

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.common import Duration
from dstack._internal.core.models.configurations import (
    PythonVersion,
    parse_apply_configuration,
)
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.unix import UnixUser
from tests._internal.pydantic_compat.compare import class_name


def _task(**overrides: Any) -> dict[str, Any]:
    return {"type": "task", "commands": ["echo hi"], **overrides}


def _service(**overrides: Any) -> dict[str, Any]:
    return {"type": "service", "commands": ["echo hi"], "port": 8000, **overrides}


class TestPythonVersionFieldParsing:
    def test_yaml_310_float_is_recovered_as_python_310(self):
        data = yaml.safe_load(
            """
            type: task
            commands: [echo hi]
            python: 3.10
            """
        )
        assert data["python"] == 3.1  # This is the lossy value the field validator receives.

        config = parse_apply_configuration(data)

        assert config.python is PythonVersion.PY310
        assert json.loads(config.json())["python"] == "3.10"

    def test_yaml_311_float_stays_python_311(self):
        data = yaml.safe_load(
            """
            type: task
            commands: [echo hi]
            python: 3.11
            """
        )

        config = parse_apply_configuration(data)

        assert config.python is PythonVersion.PY311


class TestEnvironmentFieldParsing:
    def test_list_is_normalized_to_mapping_and_missing_value_becomes_sentinel(self):
        config = parse_apply_configuration(_task(env=["A=1", "B", "EMPTY="]))

        assert config.env["A"] == "1"
        assert config.env["EMPTY"] == ""
        assert config.env["B"] == EnvSentinel(key="B")
        assert class_name(config.env["B"]) == "EnvSentinel"
        assert json.loads(config.json())["env"] == {
            "A": "1",
            "B": {"key": "B"},
            "EMPTY": "",
        }

    @pytest.mark.parametrize(
        "env",
        [
            pytest.param(["A=1", "A=2"], id="duplicate"),
            pytest.param([None], id="non-string-item"),
        ],
    )
    def test_invalid_list_entries_stay_rejected(self, env: list[Any]):
        with pytest.raises(ConfigurationError):
            parse_apply_configuration(_task(env=env))


class TestPortFieldParsing:
    def test_task_port_variants_are_normalized_to_port_mappings(self):
        config = parse_apply_configuration(_task(ports=[8080, "8081:81", "*:82"]))

        assert all(class_name(port) == "PortMapping" for port in config.ports)
        assert [port.dict() for port in config.ports] == [
            {"local_port": 8080, "container_port": 8080},
            {"local_port": 8081, "container_port": 81},
            {"local_port": None, "container_port": 82},
        ]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param(
                8000,
                {"local_port": 80, "container_port": 8000},
                id="service-container-port",
            ),
            pytest.param(
                "8080:8000",
                {"local_port": 8080, "container_port": 8000},
                id="service-mapping",
            ),
        ],
    )
    def test_service_port_variants_are_normalized(self, raw: Any, expected: dict[str, int]):
        config = parse_apply_configuration(_service(port=raw))

        assert class_name(config.port) == "PortMapping"
        assert config.port.dict() == expected


class TestMountPointFieldParsing:
    def test_string_arms_select_volume_and_instance_mount_models(self):
        config = parse_apply_configuration(
            _task(volumes=["my-volume:/mnt/data", "/host/cache:/cache"])
        )

        assert class_name(config.volumes[0]) == "VolumeMountPoint"
        assert config.volumes[0].dict() == {"name": "my-volume", "path": "/mnt/data"}
        assert class_name(config.volumes[1]) == "InstanceMountPoint"
        assert config.volumes[1].dict() == {
            "instance_path": "/host/cache",
            "path": "/cache",
            "optional": False,
        }


class TestFileMappingFieldParsing:
    def test_unix_and_windows_sources_keep_colons_in_the_source_path(self):
        config = parse_apply_configuration(
            _task(
                files=[
                    "data:/workspace/data",
                    r"C:\data:/workspace/windows",
                ]
            )
        )

        assert all(class_name(mapping) == "FilePathMapping" for mapping in config.files)
        assert [mapping.dict() for mapping in config.files] == [
            {"local_path": "data", "path": "/workspace/data"},
            {"local_path": r"C:\data", "path": "/workspace/windows"},
        ]


_REPO_CASES = [
    pytest.param(
        ".",
        {"local_path": ".", "url": None, "path": "."},
        id="local-default-target",
    ),
    pytest.param(
        "src:/workspace/src",
        {"local_path": "src", "url": None, "path": "/workspace/src"},
        id="local-explicit-target",
    ),
    pytest.param(
        "https://github.com/dstackai/dstack.git:/workspace/repo",
        {
            "local_path": None,
            "url": "https://github.com/dstackai/dstack.git",
            "path": "/workspace/repo",
        },
        id="https-url-with-target",
    ),
    pytest.param(
        "git@github.com:dstackai/dstack.git:/workspace/repo",
        {
            "local_path": None,
            "url": "git@github.com:dstackai/dstack.git",
            "path": "/workspace/repo",
        },
        id="ssh-url-with-colon-and-target",
    ),
    pytest.param(
        r"C:\src:/workspace/src",
        {"local_path": r"C:\src", "url": None, "path": "/workspace/src"},
        id="windows-source-with-target",
    ),
]


class TestRepoFieldParsing:
    @pytest.mark.parametrize(("raw", "expected"), _REPO_CASES)
    def test_repo_shorthand_is_normalized_without_splitting_url_or_drive_colons(
        self, raw: str, expected: dict[str, Any]
    ):
        config = parse_apply_configuration(_task(repos=[raw]))
        repo = config.repos[0]

        assert repo.local_path == expected["local_path"]
        assert repo.url == expected["url"]
        assert repo.path == expected["path"]


_UNIX_USER_CASES = [
    pytest.param(
        "ubuntu",
        {"uid": None, "gid": None, "username": "ubuntu", "groupname": None},
        id="username",
    ),
    pytest.param(
        "1000",
        {"uid": 1000, "gid": None, "username": None, "groupname": None},
        id="uid",
    ),
    pytest.param(
        "ubuntu:staff",
        {"uid": None, "gid": None, "username": "ubuntu", "groupname": "staff"},
        id="username-groupname",
    ),
    pytest.param(
        "1000:100",
        {"uid": 1000, "gid": 100, "username": None, "groupname": None},
        id="uid-gid",
    ),
]


class TestUnixUserFieldParsing:
    @pytest.mark.parametrize(("raw", "parsed"), _UNIX_USER_CASES)
    def test_user_field_runs_unix_user_validation_without_changing_wire_value(
        self, raw: str, parsed: dict[str, Any]
    ):
        config = parse_apply_configuration(_task(user=raw))

        assert config.user == raw
        assert UnixUser.parse(config.user).dict() == parsed

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param(":staff", id="empty-user"),
            pytest.param("ubuntu:", id="empty-group"),
            pytest.param("-1", id="negative-uid"),
            pytest.param("user:group:extra", id="too-many-parts"),
        ],
    )
    def test_invalid_user_stays_rejected(self, raw: str):
        with pytest.raises(ConfigurationError):
            parse_apply_configuration(_task(user=raw))


_DURATION_SENTINEL_CASES = [
    pytest.param("max_duration", "off", "off", str, id="max-off"),
    pytest.param("max_duration", False, "off", str, id="max-false"),
    pytest.param("stop_duration", True, None, type(None), id="stop-true"),
    pytest.param("idle_duration", "off", -1, int, id="idle-off"),
    pytest.param("idle_duration", False, -1, int, id="idle-false"),
    pytest.param("idle_duration", -1, -1, int, id="idle-legacy-minus-one"),
    pytest.param("max_duration", "2h", 7200, Duration, id="max-duration"),
]


class TestDurationSentinelFieldParsing:
    @pytest.mark.parametrize(
        ("field", "raw", "expected", "expected_type"),
        _DURATION_SENTINEL_CASES,
    )
    def test_duration_sentinel_normalization(
        self,
        field: str,
        raw: Any,
        expected: Any,
        expected_type: type,
    ):
        config = parse_apply_configuration(_task(**{field: raw}))
        value = getattr(config, field)

        assert value == expected
        assert type(value) is expected_type


class TestFleetNodesFieldParsing:
    def test_range_shorthand_sets_min_target_and_max(self):
        config = parse_apply_configuration({"type": "fleet", "nodes": "1..3"})

        assert class_name(config.nodes) == "FleetNodesSpec"
        assert config.nodes.min == 1
        assert config.nodes.target == 1
        assert config.nodes.max == 3


class TestServiceModelFieldParsing:
    def test_string_shorthand_becomes_openai_model(self):
        config = parse_apply_configuration(_service(model="llama"))

        assert class_name(config.model) == "OpenAIChatModel"
        assert config.model.dict() == {
            "type": "chat",
            "name": "llama",
            "format": "openai",
            "prefix": "/v1",
        }

    def test_tagged_tgi_mapping_stays_tgi_model(self):
        config = parse_apply_configuration(
            _service(
                model={
                    "type": "chat",
                    "name": "llama",
                    "format": "tgi",
                    "chat_template": "{{ prompt }}",
                    "eos_token": "</s>",
                }
            )
        )

        assert class_name(config.model) == "TGIChatModel"
        assert config.model.format == "tgi"


class TestGatewayReferenceFieldParsing:
    def test_project_qualified_string_becomes_entity_reference(self):
        config = parse_apply_configuration(_service(gateway="other-project/shared-gateway"))

        assert class_name(config.gateway) == "EntityReference"
        assert config.gateway.dict() == {
            "project": "other-project",
            "name": "shared-gateway",
        }
