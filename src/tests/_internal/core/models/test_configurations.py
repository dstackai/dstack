from typing import Any, Optional

import pytest

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.configurations import (
    DevEnvironmentConfigurationParams,
    PythonVersion,
    RepoSpec,
    ServiceConfiguration,
    parse_run_configuration,
)
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.routers import ReplicaGroupRouterConfig


class TestParseConfiguration:
    def test_service_model_probes_none_when_omitted(self):
        """When model is set but probes omitted, probes should remain None.
        The default probe is generated server-side in the job configurator."""
        conf = {
            "type": "service",
            "commands": ["python3 -m http.server"],
            "port": 8000,
            "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        }
        parsed = parse_run_configuration(conf)
        assert isinstance(parsed, ServiceConfiguration)
        assert parsed.probes is None

    def test_service_model_does_not_override_explicit_probes(self):
        conf = {
            "type": "service",
            "commands": ["python3 -m http.server"],
            "port": 8000,
            "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "probes": [{"type": "http", "url": "/health"}],
        }
        parsed = parse_run_configuration(conf)
        assert isinstance(parsed, ServiceConfiguration)
        assert parsed.probes is not None
        assert len(parsed.probes) == 1
        assert parsed.probes[0].url == "/health"

    def test_service_model_explicit_empty_probes_no_default(self):
        conf = {
            "type": "service",
            "commands": ["python3 -m http.server"],
            "port": 8000,
            "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "probes": [],
        }
        parsed = parse_run_configuration(conf)
        assert isinstance(parsed, ServiceConfiguration)
        assert parsed.probes is not None
        assert len(parsed.probes) == 0

    def test_services_replicas_and_scaling(self):
        def test_conf(replicas: Any, scaling: Optional[Any] = None):
            conf = {
                "type": "service",
                "commands": ["python3 -m http.server"],
                "port": 8000,
                "replicas": replicas,
            }
            if scaling:
                conf["scaling"] = scaling
            return conf

        assert parse_run_configuration(test_conf(1)).replicas == Range(min=1, max=1)
        assert parse_run_configuration(test_conf("2")).replicas == Range(min=2, max=2)
        assert parse_run_configuration(test_conf("3..3")).replicas == Range(min=3, max=3)
        with pytest.raises(
            ConfigurationError,
            match="When you set `replicas` to a range, ensure to specify `scaling`",
        ):
            parse_run_configuration(test_conf("0..10"))
        assert parse_run_configuration(
            test_conf(
                "0..10",
                {
                    "metric": "rps",
                    "target": 10,
                },
            )
        ).replicas == Range(min=0, max=10)
        with pytest.raises(
            ConfigurationError,
            match="When you set `replicas` to a range, ensure to specify `scaling`",
        ):
            parse_run_configuration(
                test_conf(
                    "0..10",
                    {
                        "metric": "rpc",
                        "target": 10,
                    },
                )
            )

    def test_replica_group_router(self):
        conf = {
            "type": "service",
            "port": 8000,
            "replicas": [
                {
                    "name": "router",
                    "count": 1,
                    "commands": ["sglang serve"],
                    "router": {"type": "sglang"},
                },
                {"name": "worker", "count": 2, "commands": ["worker"]},
            ],
        }
        parsed = parse_run_configuration(conf)
        assert isinstance(parsed, ServiceConfiguration)
        assert parsed.replicas is not None
        assert isinstance(parsed.replicas, list)
        router_g = next(g for g in parsed.replicas if g.name == "router")
        assert isinstance(router_g.router, ReplicaGroupRouterConfig)
        assert router_g.router.type == "sglang"

    def test_replica_group_router_forbids_service_level_router(self):
        conf = {
            "type": "service",
            "port": 8000,
            "router": {"type": "sglang"},
            "replicas": [
                {
                    "name": "router",
                    "count": 1,
                    "commands": ["sglang serve"],
                    "router": {"type": "sglang"},
                },
                {"name": "worker", "count": 2, "commands": ["worker"]},
            ],
        }
        with pytest.raises(
            ConfigurationError,
            match="Service-Level router configuration is not allowed together with replica-group",
        ):
            parse_run_configuration(conf)

    @pytest.mark.parametrize("shell", [None, "sh", "bash", "/usr/bin/zsh"])
    def test_shell_valid(self, shell: Optional[str]):
        conf = {
            "type": "task",
            "shell": shell,
            "commands": ["sleep inf"],
        }
        assert parse_run_configuration(conf).shell == shell

    def test_shell_invalid(self):
        conf = {
            "type": "task",
            "shell": "zsh",
            "commands": ["sleep inf"],
        }
        with pytest.raises(
            ConfigurationError, match="The value must be `sh`, `bash`, or an absolute path"
        ):
            parse_run_configuration(conf)


class TestReplicaGroupContainerFields:
    """Per-replica-group image-source fields: `image`, `docker`, `python`,
    `nvcc`, `privileged`. Covers field-level mutex validators, the
    cross-level no-mixing validator, the runnable-check validator, and
    YAML coercion for `python`."""

    def test_replica_group_accepts_image_python_nvcc_docker(self):
        conf = {
            "type": "service",
            "port": 8000,
            "replicas": [
                {"name": "a", "count": 1, "image": "nginx:latest", "commands": ["x"]},
                {"name": "b", "count": 1, "python": "3.12", "commands": ["x"]},
                {"name": "c", "count": 1, "nvcc": True, "commands": ["x"]},
                {"name": "d", "count": 1, "docker": True, "commands": ["x"]},
            ],
        }
        parsed = parse_run_configuration(conf)
        assert isinstance(parsed, ServiceConfiguration)
        groups = {g.name: g for g in parsed.replicas}
        assert groups["a"].image == "nginx:latest"
        assert groups["b"].python == PythonVersion.PY312
        assert groups["c"].nvcc is True
        assert groups["d"].docker is True

    def test_replica_group_accepts_privileged(self):
        conf = {
            "type": "service",
            "port": 8000,
            "replicas": [
                {
                    "name": "a",
                    "count": 1,
                    "image": "x",
                    "privileged": True,
                    "commands": ["x"],
                },
            ],
        }
        parsed = parse_run_configuration(conf)
        assert parsed.replicas[0].privileged is True

    @pytest.mark.parametrize(
        "yaml_value,expected",
        [
            (3.10, PythonVersion.PY310),
            (3.12, PythonVersion.PY312),
            ("3.10", PythonVersion.PY310),
            ("3.12", PythonVersion.PY312),
        ],
    )
    def test_replica_group_python_yaml_coercion(self, yaml_value, expected):
        """YAML may parse `3.10` as float 3.1 — must coerce back to '3.10'."""
        conf = {
            "type": "service",
            "port": 8000,
            "replicas": [{"count": 1, "python": yaml_value, "commands": ["x"]}],
        }
        parsed = parse_run_configuration(conf)
        assert parsed.replicas[0].python == expected

    def test_replica_group_image_python_mutex(self):
        with pytest.raises(
            ConfigurationError,
            match="`image` and `python` are mutually exclusive",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "replicas": [
                        {"count": 1, "image": "x", "python": "3.12", "commands": ["x"]},
                    ],
                }
            )

    def test_replica_group_image_docker_mutex(self):
        with pytest.raises(
            ConfigurationError,
            match="`image` and `docker` are mutually exclusive",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "replicas": [
                        {"count": 1, "image": "x", "docker": True, "commands": ["x"]},
                    ],
                }
            )

    def test_replica_group_python_docker_mutex(self):
        with pytest.raises(
            ConfigurationError,
            match="`python` and `docker` are mutually exclusive",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "replicas": [
                        {"count": 1, "python": "3.12", "docker": True, "commands": ["x"]},
                    ],
                }
            )

    def test_replica_group_nvcc_docker_mutex(self):
        with pytest.raises(
            ConfigurationError,
            match="`nvcc` and `docker` are mutually exclusive",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "replicas": [
                        {"count": 1, "nvcc": True, "docker": True, "commands": ["x"]},
                    ],
                }
            )

    def test_replica_group_python_nvcc_allowed_together(self):
        """python + nvcc is the dstackai/base + CUDA combo, must be allowed."""
        conf = {
            "type": "service",
            "port": 8000,
            "replicas": [
                {"count": 1, "python": "3.12", "nvcc": True, "commands": ["x"]},
            ],
        }
        parsed = parse_run_configuration(conf)
        assert parsed.replicas[0].python == PythonVersion.PY312
        assert parsed.replicas[0].nvcc is True

    def test_replica_group_docker_with_privileged_false_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="`privileged: false` is incompatible with `docker: true`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "replicas": [
                        {
                            "count": 1,
                            "docker": True,
                            "privileged": False,
                            "commands": ["x"],
                        },
                    ],
                }
            )

    def test_replica_group_docker_with_privileged_unset_allowed(self):
        parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "replicas": [
                    {"count": 1, "docker": True, "commands": ["x"]},
                ],
            }
        )

    def test_image_set_at_both_service_and_group_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="`image` is set at both",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "image": "svc:1.0",
                    "replicas": [
                        {"count": 1, "image": "grp:1.0", "commands": ["x"]},
                    ],
                }
            )

    def test_docker_set_at_both_service_and_group_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="`docker` is set at both",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "docker": True,
                    "replicas": [
                        {"count": 1, "docker": True, "commands": ["x"]},
                    ],
                }
            )

    def test_python_set_at_both_service_and_group_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="`python` is set at both",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "python": "3.12",
                    "replicas": [
                        {"count": 1, "python": "3.12", "commands": ["x"]},
                    ],
                }
            )

    def test_nvcc_set_at_both_service_and_group_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="`nvcc` is set at both",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "nvcc": True,
                    "replicas": [
                        {"count": 1, "nvcc": True, "commands": ["x"]},
                    ],
                }
            )

    def test_privileged_set_at_both_service_and_group_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="`privileged` is set at both",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "privileged": True,
                    "replicas": [
                        {
                            "count": 1,
                            "image": "x",
                            "privileged": True,
                            "commands": ["x"],
                        },
                    ],
                }
            )

    def test_image_at_service_with_groups_inheriting_allowed(self):
        parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "image": "svc:1.0",
                "replicas": [
                    {"count": 1, "commands": ["x"]},
                    {"count": 1, "commands": ["x"]},
                ],
            }
        )

    def test_docker_at_service_with_groups_inheriting_allowed(self):
        """Service-level `docker: true` combined with groups that don't set
        docker should parse cleanly — groups inherit the service-level value.
        Guards against the no-mixing validator accidentally rejecting the
        inherit case."""
        parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "docker": True,
                "replicas": [
                    {"count": 1, "commands": ["x"]},
                    {"count": 1, "commands": ["x"]},
                ],
            }
        )

    def test_partial_mix_rejected(self):
        """Service sets image; only one group overrides — still a mix."""
        with pytest.raises(
            ConfigurationError,
            match=r"replica group\(s\) \['b'\]",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "image": "svc:1.0",
                    "replicas": [
                        {"name": "a", "count": 1, "commands": ["x"]},
                        {"name": "b", "count": 1, "image": "g:2", "commands": ["x"]},
                    ],
                }
            )

    def test_replica_group_with_only_image_no_commands_allowed(self):
        parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "replicas": [{"count": 1, "image": "nginx:latest"}],
            }
        )

    def test_replica_group_with_only_python_no_commands_allowed(self):
        parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "replicas": [{"count": 1, "python": "3.12"}],
            }
        )

    def test_replica_group_with_only_nvcc_no_commands_allowed(self):
        parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "replicas": [{"count": 1, "nvcc": True}],
            }
        )

    def test_empty_replica_group_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="has nothing to run",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "replicas": [{"count": 1}],
                }
            )

    def test_service_level_image_satisfies_groups_runnable_check(self):
        parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "image": "svc:1.0",
                "replicas": [{"count": 1}, {"count": 1}],
            }
        )


class TestRepoSpec:
    @pytest.mark.parametrize("value", [".", "rel/path", "/abs/path/"])
    def test_parse_local_path_no_path(self, value: str):
        assert RepoSpec.parse(value) == RepoSpec(local_path=value, path=".")

    @pytest.mark.parametrize(
        ["value", "expected_repo_path"],
        [[".:/repo", "."], ["rel/path:/repo", "rel/path"], ["/abs/path/:/repo", "/abs/path/"]],
    )
    def test_parse_local_path_with_path(self, value: str, expected_repo_path: str):
        assert RepoSpec.parse(value) == RepoSpec(local_path=expected_repo_path, path="/repo")

    def test_parse_windows_abs_local_path_no_path(self):
        assert RepoSpec.parse("C:\\repo") == RepoSpec(local_path="C:\\repo", path=".")

    def test_parse_windows_abs_local_path_with_path(self):
        assert RepoSpec.parse("C:\\repo:/repo") == RepoSpec(local_path="C:\\repo", path="/repo")

    def test_parse_url_no_path(self):
        assert RepoSpec.parse("https://example.com/repo.git") == RepoSpec(
            url="https://example.com/repo.git", path="."
        )

    def test_parse_url_with_path(self):
        assert RepoSpec.parse("https://example.com/repo.git:/repo") == RepoSpec(
            url="https://example.com/repo.git", path="/repo"
        )

    def test_parse_scp_no_path(self):
        assert RepoSpec.parse("git@example.com:repo.git") == RepoSpec(
            url="git@example.com:repo.git", path="."
        )

    def test_parse_scp_with_path(self):
        assert RepoSpec.parse("git@example.com:repo.git:/repo") == RepoSpec(
            url="git@example.com:repo.git", path="/repo"
        )

    @pytest.mark.parametrize("path", ["~", "~/repo"])
    def test_path_tilde(self, path: str):
        assert RepoSpec(local_path=".", path=path).path == path

    def test_error_invalid_mapping_if_more_than_two_parts(self):
        with pytest.raises(ValueError, match="Invalid repo"):
            RepoSpec.parse("./foo:bar:baz")

    def test_error_local_path_url_mutually_exclusive(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            RepoSpec(local_path=".", url="https://example.com/repo.git")

    def test_error_local_path_or_url_required(self):
        with pytest.raises(ValueError, match="must be specified"):
            RepoSpec()

    def test_error_path_tilde_username_not_supported(self):
        with pytest.raises(ValueError, match="syntax is not supported"):
            RepoSpec(local_path=".", path="~alice/repo")


def test_registry_auth_hashable():
    """
    RegistryAuth instances should be hashable
    to be used as cache keys in _get_image_config
    """
    registry_auth = RegistryAuth(username="username", password="password")
    hash(registry_auth)


class TestDevEnvironmentConfigurationParams:
    def test_windsurf_version_valid_format(self):
        params = DevEnvironmentConfigurationParams(
            ide="windsurf", version="1.106.0@8951cd3ad688e789573d7f51750d67ae4a0bea7d"
        )
        assert params.ide == "windsurf"
        assert params.version == "1.106.0@8951cd3ad688e789573d7f51750d67ae4a0bea7d"

    def test_windsurf_version_valid_short_commit(self):
        params = DevEnvironmentConfigurationParams(ide="windsurf", version="1.0.0@abc123")
        assert params.version == "1.0.0@abc123"

    def test_windsurf_version_empty_allowed(self):
        params = DevEnvironmentConfigurationParams(ide="windsurf", version=None)
        assert params.ide == "windsurf"
        assert params.version is None

    def test_windsurf_version_invalid_missing_at(self):
        with pytest.raises(ValueError, match="Invalid Windsurf version format"):
            DevEnvironmentConfigurationParams(ide="windsurf", version="1.106.0")

    def test_windsurf_version_invalid_missing_commit(self):
        with pytest.raises(ValueError, match="Invalid Windsurf version format"):
            DevEnvironmentConfigurationParams(ide="windsurf", version="1.106.0@")

    def test_windsurf_version_invalid_missing_version(self):
        with pytest.raises(ValueError, match="Invalid Windsurf version format"):
            DevEnvironmentConfigurationParams(
                ide="windsurf", version="@8951cd3ad688e789573d7f51750d67ae4a0bea7d"
            )

    def test_windsurf_version_invalid_non_hex_commit(self):
        with pytest.raises(ValueError, match="Invalid Windsurf version format"):
            DevEnvironmentConfigurationParams(ide="windsurf", version="1.106.0@ghijklmnop")

    def test_vscode_version_not_validated(self):
        params = DevEnvironmentConfigurationParams(ide="vscode", version="1.80.0")
        assert params.ide == "vscode"
        assert params.version == "1.80.0"

    def test_cursor_version_not_validated(self):
        params = DevEnvironmentConfigurationParams(ide="cursor", version="0.40.0")
        assert params.ide == "cursor"
        assert params.version == "0.40.0"

    def test_ide_optional(self):
        params = DevEnvironmentConfigurationParams()
        assert params.ide is None
        assert params.version is None

    def test_version_requires_ide(self):
        with pytest.raises(ValueError, match="`version` requires `ide` to be set"):
            DevEnvironmentConfigurationParams(version="1.80.0")
