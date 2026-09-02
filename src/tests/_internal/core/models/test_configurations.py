from copy import deepcopy
from typing import Any, Optional

import pytest
from pydantic import ValidationError

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.configurations import (
    DevEnvironmentConfigurationParams,
    PresetConfiguration,
    PresetModelBase,
    PresetModelRepo,
    PythonVersion,
    RepoSpec,
    ServiceConfiguration,
    parse_run_configuration,
)
from dstack._internal.core.models.resources import Range, ResourcesSpec
from dstack._internal.core.models.routers import ReplicaGroupRouterConfig


class TestParseConfiguration:
    @pytest.mark.parametrize("configuration_type", ["task", "dev-environment", "service"])
    def test_server_access_supported(self, configuration_type: str):
        conf = {"type": configuration_type, "dstack": True}
        if configuration_type == "task":
            conf["commands"] = ["true"]
        elif configuration_type == "service":
            conf["commands"] = ["true"]
            conf["port"] = 8000

        parsed = parse_run_configuration(conf)

        assert parsed.dstack is True

    def test_server_access_not_supported_with_inactivity_duration(self):
        with pytest.raises(ConfigurationError, match="inactivity_duration"):
            parse_run_configuration(
                {
                    "type": "dev-environment",
                    "dstack": True,
                    "inactivity_duration": "1h",
                }
            )

    def test_server_access_and_inactivity_duration_allowed_separately(self):
        parse_run_configuration({"type": "dev-environment", "dstack": True})
        parse_run_configuration({"type": "dev-environment", "inactivity_duration": "1h"})

    def test_server_access_allows_unresolved_passthrough_env(self):
        parsed = parse_run_configuration(
            {
                "type": "task",
                "commands": ["true"],
                "dstack": True,
                "env": ["DSTACK_TOKEN"],
            }
        )

        assert "DSTACK_TOKEN" in parsed.env

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
        # `metric: rpc` is a typo, so `scaling` itself fails to validate. The config stays
        # rejected, but the message is no longer the `scaling`-is-missing one: pydantic v1 ran a
        # bare `root_validator` even after a field had failed, handing it a partial `values` dict
        # in which `scaling` was absent. A v2 `model_validator(mode="after")` does not run at all
        # once a field is invalid, so what surfaces is the actual typo — the more precise error.
        with pytest.raises(ConfigurationError, match="metric"):
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
        assert parsed.groups is not None
        router_g = next(g for g in parsed.groups if g.name == "router")
        assert isinstance(router_g.router, ReplicaGroupRouterConfig)
        assert router_g.router.type == "sglang"

    def test_spot_policy_set_at_both_service_and_group_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="`spot_policy` is set at both",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "spot_policy": "spot",
                    "replicas": [
                        {
                            "count": 1,
                            "commands": ["x"],
                            "spot_policy": "on-demand",
                        },
                    ],
                }
            )

    def test_reservation_set_at_both_service_and_group_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="`reservation` is set at both",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "image": "x",
                    "reservation": "svc-res",
                    "replicas": [
                        {
                            "count": 1,
                            "reservation": "grp-res",
                        },
                    ],
                }
            )

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
        assert parsed.groups is not None
        groups = {g.name: g for g in parsed.groups}
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
        assert isinstance(parsed, ServiceConfiguration)
        assert parsed.groups is not None
        assert parsed.groups[0].privileged is True

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
        assert isinstance(parsed, ServiceConfiguration)
        assert parsed.groups is not None
        assert parsed.groups[0].python == expected

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
        assert isinstance(parsed, ServiceConfiguration)
        assert parsed.groups is not None
        assert parsed.groups[0].python == PythonVersion.PY312
        assert parsed.groups[0].nvcc is True

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

    # ---- Cross-level conflicting image sources ----
    # Validates `validate_no_conflicting_image_sources_across_levels`.

    def test_service_image_conflicts_with_group_docker_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="Service-level `image` conflicts with group-level `docker`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "image": "alpine",
                    "replicas": [{"count": 1, "docker": True, "commands": ["x"]}],
                }
            )

    def test_service_image_conflicts_with_group_python_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="Service-level `image` conflicts with group-level `python`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "image": "alpine",
                    "replicas": [{"count": 1, "python": "3.12", "commands": ["x"]}],
                }
            )

    def test_service_image_conflicts_with_group_nvcc_rejected(self):
        """Reviewer's exact example."""
        with pytest.raises(
            ConfigurationError,
            match="Service-level `image` conflicts with group-level `nvcc`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "image": "alpine",
                    "replicas": [{"count": 1, "nvcc": True, "commands": ["x"]}],
                }
            )

    def test_service_docker_conflicts_with_group_image_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="Service-level `docker` conflicts with group-level `image`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "docker": True,
                    "replicas": [{"count": 1, "image": "alpine", "commands": ["x"]}],
                }
            )

    def test_service_docker_conflicts_with_group_python_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="Service-level `docker` conflicts with group-level `python`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "docker": True,
                    "replicas": [{"count": 1, "python": "3.12", "commands": ["x"]}],
                }
            )

    def test_service_docker_conflicts_with_group_nvcc_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="Service-level `docker` conflicts with group-level `nvcc`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "docker": True,
                    "replicas": [{"count": 1, "nvcc": True, "commands": ["x"]}],
                }
            )

    def test_service_python_conflicts_with_group_image_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="Service-level `python` conflicts with group-level `image`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "python": "3.12",
                    "replicas": [{"count": 1, "image": "alpine", "commands": ["x"]}],
                }
            )

    def test_service_python_conflicts_with_group_docker_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="Service-level `python` conflicts with group-level `docker`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "python": "3.12",
                    "replicas": [{"count": 1, "docker": True, "commands": ["x"]}],
                }
            )

    def test_service_nvcc_conflicts_with_group_image_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="Service-level `nvcc` conflicts with group-level `image`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "nvcc": True,
                    "replicas": [{"count": 1, "image": "alpine", "commands": ["x"]}],
                }
            )

    def test_service_nvcc_conflicts_with_group_docker_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="Service-level `nvcc` conflicts with group-level `docker`",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "nvcc": True,
                    "replicas": [{"count": 1, "docker": True, "commands": ["x"]}],
                }
            )

    def test_service_python_with_group_nvcc_allowed(self):
        """`python` and `nvcc` are compatible base-image knobs and may
        coexist across levels."""
        parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "python": "3.12",
                "replicas": [{"count": 1, "nvcc": True, "commands": ["x"]}],
            }
        )

    def test_service_nvcc_with_group_python_allowed(self):
        parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "nvcc": True,
                "replicas": [{"count": 1, "python": "3.12", "commands": ["x"]}],
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

    def test_replica_group_with_only_python_no_commands_rejected(self):
        """`python` configures the base image but doesn't supply a runnable
        workload — must be paired with `commands` or `image`. Matches
        service-level behavior."""
        with pytest.raises(
            ConfigurationError,
            match="either `commands` or `image` must be set",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "replicas": [{"count": 1, "python": "3.12"}],
                }
            )

    def test_replica_group_with_only_nvcc_no_commands_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="either `commands` or `image` must be set",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "replicas": [{"count": 1, "nvcc": True}],
                }
            )

    def test_replica_group_with_only_docker_no_commands_rejected(self):
        """`docker: true` runs DIND but injects only `start-dockerd`;
        without user commands the replica has no actual workload."""
        with pytest.raises(
            ConfigurationError,
            match="either `commands` or `image` must be set",
        ):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "replicas": [{"count": 1, "docker": True}],
                }
            )

    def test_empty_replica_group_rejected(self):
        with pytest.raises(
            ConfigurationError,
            match="either `commands` or `image` must be set",
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

    def test_zed_ide_allowed(self):
        params = DevEnvironmentConfigurationParams(ide="zed")
        assert params.ide == "zed"
        assert params.version is None

    def test_zed_version_not_validated(self):
        params = DevEnvironmentConfigurationParams(ide="zed", version="0.100.0")
        assert params.ide == "zed"
        assert params.version == "0.100.0"

    def test_ide_optional(self):
        params = DevEnvironmentConfigurationParams()
        assert params.ide is None
        assert params.version is None

    def test_version_requires_ide(self):
        with pytest.raises(ValueError, match="`version` requires `ide` to be set"):
            DevEnvironmentConfigurationParams(version="1.80.0")


class TestNodeGroups:
    def test_parses_int_nodes(self):
        parsed = parse_run_configuration({"type": "task", "nodes": 2, "commands": ["true"]})
        assert parsed.type == "task"
        assert parsed.nodes == 2
        assert parsed.groups is None
        assert parsed.nodes_num == 2
        assert len(parsed.node_groups) == 1
        assert parsed.node_groups[0].nodes == 2
        assert parsed.node_groups[0].name == "0"

    def test_parses_groups_and_defaults_names(self):
        parsed = parse_run_configuration(
            {
                "type": "task",
                "image": "debian",
                "groups": [
                    {"nodes": 2, "commands": ["echo head"]},
                    {"name": "workers", "nodes": 1, "commands": ["echo worker"]},
                ],
            }
        )
        assert parsed.type == "task"
        assert parsed.groups is not None
        assert parsed.nodes_num == 3
        assert parsed.node_groups[0].name == "0"
        assert parsed.node_groups[1].name == "workers"
        assert parsed.node_groups[0].commands == ["echo head"]
        assert parsed.node_groups[1].commands == ["echo worker"]

    def test_rejects_nodes_with_groups(self):
        with pytest.raises(
            ConfigurationError, match="`nodes` and `groups` are mutually exclusive"
        ):
            parse_run_configuration(
                {
                    "type": "task",
                    "image": "debian",
                    "nodes": 1,
                    "groups": [
                        {"nodes": 2, "commands": ["echo head"]},
                        {"name": "workers", "nodes": 1, "commands": ["echo worker"]},
                    ],
                }
            )

    def test_omitted_nodes_defaults_to_one_node_group(self):
        parsed = parse_run_configuration({"type": "task", "commands": ["true"]})
        assert parsed.nodes is None
        assert parsed.nodes_num == 1
        assert parsed.node_groups[0].nodes == 1

    def test_groups_round_trip_via_model_dump(self):
        parsed = parse_run_configuration(
            {
                "type": "task",
                "image": "debian",
                "groups": [
                    {"nodes": 2, "commands": ["echo head"], "ports": [8000]},
                    {"name": "workers", "nodes": 1, "commands": ["echo worker"]},
                ],
            }
        )
        assert parsed.type == "task"
        dumped = parsed.model_dump(mode="json")
        assert dumped["nodes"] is None
        assert dumped["groups"] is not None

        reparsed = parse_run_configuration(dumped)
        assert reparsed.type == "task"
        assert reparsed.nodes is None
        assert reparsed.nodes_num == 3
        assert [g.name for g in reparsed.node_groups] == ["0", "workers"]
        assert reparsed.node_groups[0].commands == ["echo head"]
        assert reparsed.node_groups[0].ports[0].container_port == 8000
        assert reparsed.node_groups[1].commands == ["echo worker"]

    def test_rejects_auto_name_collision_with_explicit_name(self):
        # Unnamed group at index 1 becomes "1", colliding with an explicit name "1".
        with pytest.raises(ConfigurationError, match="Duplicate node group names"):
            parse_run_configuration(
                {
                    "type": "task",
                    "image": "debian",
                    "groups": [
                        {"name": "1", "nodes": 1, "commands": ["true"]},
                        {"nodes": 1, "commands": ["true"]},
                    ],
                }
            )

    def test_rejects_duplicate_group_names(self):
        with pytest.raises(ConfigurationError, match="Duplicate node group names"):
            parse_run_configuration(
                {
                    "type": "task",
                    "image": "debian",
                    "groups": [
                        {"name": "head", "nodes": 1, "commands": ["true"]},
                        {"name": "head", "nodes": 1, "commands": ["true"]},
                    ],
                }
            )

    def test_rejects_invalid_group_name(self):
        with pytest.raises(ConfigurationError, match="Node group name should match regex"):
            parse_run_configuration(
                {
                    "type": "task",
                    "image": "debian",
                    "groups": [{"name": "Bad_Name", "nodes": 1, "commands": ["true"]}],
                }
            )

    def test_rejects_empty_groups(self):
        with pytest.raises(ConfigurationError, match="cannot be an empty list"):
            parse_run_configuration({"type": "task", "image": "debian", "groups": []})

    def test_rejects_nodes_and_groups_together(self):
        with pytest.raises(ConfigurationError, match="mutually exclusive"):
            parse_run_configuration(
                {
                    "type": "task",
                    "image": "debian",
                    "nodes": 2,
                    "groups": [{"nodes": 1, "commands": ["true"]}],
                }
            )

    def test_rejects_top_level_commands_with_groups(self):
        with pytest.raises(ConfigurationError, match="Top-level `commands` is not allowed"):
            parse_run_configuration(
                {
                    "type": "task",
                    "image": "debian",
                    "commands": ["echo top"],
                    "groups": [{"nodes": 1, "commands": ["echo group"]}],
                }
            )

    def test_rejects_top_level_ports_with_groups(self):
        with pytest.raises(ConfigurationError, match="Top-level `ports` is not allowed"):
            parse_run_configuration(
                {
                    "type": "task",
                    "image": "debian",
                    "ports": [8000],
                    "groups": [{"nodes": 1, "commands": ["true"]}],
                }
            )

    def test_rejects_top_level_entrypoint_with_groups(self):
        with pytest.raises(ConfigurationError, match="Top-level `entrypoint` is not allowed"):
            parse_run_configuration(
                {
                    "type": "task",
                    "image": "debian",
                    "entrypoint": "python",
                    "groups": [{"nodes": 1, "commands": ["echo ok"]}],
                }
            )

    def test_rejects_group_without_commands_or_image(self):
        with pytest.raises(ConfigurationError, match="either `commands` must be set"):
            parse_run_configuration(
                {
                    "type": "task",
                    "groups": [{"name": "head", "nodes": 1}],
                }
            )

    def test_accepts_top_level_resources_with_groups(self):
        """Top-level resources is allowed (not rejected) but not used for group jobs."""
        parsed = parse_run_configuration(
            {
                "type": "task",
                "image": "debian",
                "resources": {"gpu": "H100"},
                "groups": [{"nodes": 1, "commands": ["true"]}],
            }
        )
        assert parsed.groups is not None
        assert parsed.groups[0].resources == ResourcesSpec()
        assert parsed.resources.gpu is not None
        assert parsed.resources.gpu.name == ["H100"]


class TestServiceGroupsPhase1:
    def test_legacy_replicas_list_parses_to_groups(self):
        parsed = parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "replicas": [{"count": 1, "commands": ["x"]}],
            }
        )
        assert isinstance(parsed, ServiceConfiguration)
        assert parsed.replicas is None
        assert parsed.groups is not None
        assert parsed.groups[0].replicas == Range(min=1, max=1)

    def test_new_groups_syntax_parses_identically(self):
        legacy = parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "replicas": [{"count": 1, "commands": ["x"]}],
            }
        )
        new = parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "groups": [{"replicas": 1, "commands": ["x"]}],
            }
        )
        assert isinstance(legacy, ServiceConfiguration)
        assert isinstance(new, ServiceConfiguration)
        assert legacy.replicas is None
        assert new.replicas is None
        assert legacy.groups == new.groups

    def test_dump_is_groups_canonical(self):
        parsed = parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "groups": [{"replicas": 1, "commands": ["x"]}],
            }
        )
        # The legacy `replicas: [{count: ...}]` shape is produced only for old
        # clients, by `server/compatibility/runs.py`, not by the model.
        dumped = parsed.model_dump()
        assert dumped["replicas"] is None
        assert isinstance(dumped["groups"], list)
        assert "replicas" in dumped["groups"][0]
        assert "count" not in dumped["groups"][0]
        dumped_json = parsed.model_dump(mode="json")
        assert dumped_json["replicas"] is None
        assert "replicas" in dumped_json["groups"][0]

    def test_dump_validate_is_fixed_point(self):
        parsed = parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "groups": [{"replicas": 1, "commands": ["x"]}],
            }
        )
        assert isinstance(parsed, ServiceConfiguration)
        once = ServiceConfiguration.model_validate(parsed.model_dump())
        twice = ServiceConfiguration.model_validate(once.model_dump())
        assert once.model_dump() == twice.model_dump() == parsed.model_dump()

    def test_homogeneous_dump_has_null_groups(self):
        parsed = parse_run_configuration(
            {
                "type": "service",
                "port": 8000,
                "commands": ["x"],
                "replicas": 2,
            }
        )
        # Nothing strips the key now that the model no longer rewrites groups.
        dumped = parsed.model_dump()
        assert dumped["groups"] is None
        assert dumped["replicas"] == {"min": 2, "max": 2}

    def test_replicas_and_groups_rejected(self):
        with pytest.raises(ConfigurationError, match="mutually exclusive"):
            parse_run_configuration(
                {
                    "type": "service",
                    "port": 8000,
                    "replicas": 2,
                    "groups": [{"replicas": 1, "commands": ["x"]}],
                }
            )

    def test_empty_groups_rejected(self):
        with pytest.raises(ConfigurationError, match="empty"):
            parse_run_configuration({"type": "service", "port": 8000, "groups": []})

    def test_parse_does_not_mutate_caller_dict(self):
        conf = {
            "type": "service",
            "port": 8000,
            "replicas": [{"count": 1, "commands": ["x"]}],
        }
        original = deepcopy(conf)
        parse_run_configuration(conf)
        assert conf == original
        assert conf["replicas"][0]["count"] == 1


class TestPresetConfiguration:
    def test_schema_documents_supported_input(self):
        assert all(field.description for field in PresetConfiguration.model_fields.values())
        assert all(field.description for field in PresetModelBase.model_fields.values())
        assert all(field.description for field in PresetModelRepo.model_fields.values())
        assert {"type": "string"} in PresetConfiguration.model_json_schema()["properties"][
            "model"
        ]["anyOf"]

    def test_parses_string_as_exact_repo(self):
        configuration = PresetConfiguration(model="Qwen/Qwen3.5-27B")

        assert isinstance(configuration.model, PresetModelRepo)
        assert configuration.model.exact_repo == "Qwen/Qwen3.5-27B"
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"
        assert not configuration.model.allows_variant_selection

    def test_parses_base_model(self):
        configuration = PresetConfiguration(base="Qwen/Qwen3.5-27B")

        assert isinstance(configuration.model, PresetModelBase)
        assert configuration.model.exact_repo is None
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"
        assert configuration.model.allows_variant_selection

    def test_parses_exact_repo_with_client_facing_name(self):
        configuration = PresetConfiguration(
            model={
                "repo": "community/Qwen3.5-27B-GPTQ-Int4",
                "name": "Qwen/Qwen3.5-27B",
            }
        )

        assert configuration.model.exact_repo == "community/Qwen3.5-27B-GPTQ-Int4"
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"

    def test_rejects_ambiguous_model_object(self):
        with pytest.raises(ValidationError):
            PresetConfiguration(model={"base": "Qwen/base", "repo": "Qwen/repo"})

    def test_parses_top_level_base_shorthand(self):
        configuration = PresetConfiguration(base="Qwen/Qwen3.5-27B")

        assert isinstance(configuration.model, PresetModelBase)
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"
        assert configuration.base is None

    def test_parses_top_level_repo_shorthand(self):
        configuration = PresetConfiguration(repo="community/Qwen3.5-27B-GPTQ-Int4")

        assert isinstance(configuration.model, PresetModelRepo)
        assert configuration.model.exact_repo == "community/Qwen3.5-27B-GPTQ-Int4"
        assert configuration.repo is None

    def test_shorthand_round_trips_through_dict(self):
        configuration = PresetConfiguration(base="Qwen/Qwen3.5-27B")

        round_tripped = PresetConfiguration.model_validate(configuration.model_dump())

        assert round_tripped.model == configuration.model

    def test_rejects_combined_base_and_repo_shorthand(self):
        with pytest.raises(ValidationError):
            PresetConfiguration(base="Qwen/base", repo="Qwen/repo")

    def test_rejects_shorthand_combined_with_model(self):
        with pytest.raises(ValidationError, match="cannot be combined"):
            PresetConfiguration(base="Qwen/base", model={"repo": "Qwen/repo"})

    def test_requires_model(self):
        with pytest.raises(ValidationError):
            PresetConfiguration()

    @pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "shared_prefix_tokens"])
    def test_rejects_request_shape_fields_with_a_custom_dataset(self, field):
        with pytest.raises(ValidationError, match="cannot be set together with `dataset`"):
            PresetConfiguration(base="Qwen/Qwen3.5-27B", dataset="spec_bench", **{field: 512})

    def test_allows_request_shape_fields_without_a_dataset(self):
        configuration = PresetConfiguration(
            base="Qwen/Qwen3.5-27B", input_tokens=1024, output_tokens=256
        )

        assert configuration.input_tokens == 1024
        assert configuration.output_tokens == 256

    def test_rejects_the_retired_random_alias(self):
        # `random` used to be the explicit way to ask for synthetic prompts;
        # now a set dataset always means a real one.
        with pytest.raises(ValidationError, match="omit `dataset` for synthetic prompts"):
            PresetConfiguration(base="Qwen/Qwen3.5-27B", dataset="random")

    def test_defaults_to_a_synthetic_workload(self):
        configuration = PresetConfiguration(base="Qwen/Qwen3.5-27B")

        assert configuration.dataset is None


class TestPresetConfigurationSchema:
    def test_schema_does_not_require_model(self):
        # `model` is filled from the `base`/`repo` shorthand by a before-validator,
        # which JSON Schema consumers (IDEs) never run.
        schema = PresetConfiguration.model_json_schema()
        assert "model" not in schema.get("required", [])
        for field in ("model", "base", "repo"):
            assert field in schema["properties"]
