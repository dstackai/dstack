import re
import uuid
from types import SimpleNamespace
from typing import Any, Optional

import gpuhunt
import pytest

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import (
    NodeGroup,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.files import FileArchiveMapping
from dstack._internal.core.models.profiles import Profile, ProfileRetry
from dstack._internal.core.models.repos.local import LocalRunRepoData
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.services.runs.spec import (
    _check_can_update_configuration,
    check_can_update_run_spec,
    run_spec_has_replica_ip_refs,
    set_run_spec_resources_defaults,
    validate_run_spec_and_set_defaults,
)
from dstack._internal.server.testing.common import get_run_spec


def _service_configuration(
    *,
    router_type=None,
    image=None,
    env=None,
    worker_count_min=None,
    router_commands="echo router",
    worker_commands="echo worker",
):
    # Build a ServiceConfiguration instance for the in-place update tests.
    worker = {
        "name": "worker",
        "commands": [worker_commands],
    }
    if worker_count_min is None:
        worker["count"] = 1
    else:
        worker["count"] = {"min": worker_count_min, "max": worker_count_min + 1}
        worker["scaling"] = {"metric": "rps", "target": 4}
    replicas = [worker]
    if router_type is not None:
        replicas.append(
            {
                "name": "router",
                "router": {"type": router_type},
                "commands": [router_commands],
                "count": 1,
            }
        )
    data = {
        "type": "service",
        "port": 8000,
        "replicas": replicas,
    }
    if image is not None:
        data["image"] = image
    if env is not None:
        data["env"] = env
    return ServiceConfiguration.model_validate(data)


def _service_with_groups(groups: list[dict]) -> ServiceConfiguration:
    return ServiceConfiguration.model_validate(
        {
            "type": "service",
            "port": 8000,
            "image": "debian",
            "groups": groups,
        }
    )


def _run_spec(configuration: ServiceConfiguration, **kwargs):
    return get_run_spec(
        repo_id="test-repo", run_name="test-run", configuration=configuration, **kwargs
    )


def _run_spec_with_overrides(configuration: ServiceConfiguration, **overrides) -> RunSpec:
    get_run_spec_keys = {"repo_code_hash", "repo_data"}
    get_run_spec_kwargs = {k: v for k, v in overrides.items() if k in get_run_spec_keys}
    run_spec_overrides = {k: v for k, v in overrides.items() if k not in get_run_spec_keys}
    run_spec = get_run_spec(
        repo_id="test-repo",
        run_name="test-run",
        configuration=configuration,
        **get_run_spec_kwargs,
    )
    if not run_spec_overrides:
        return run_spec
    return RunSpec.model_validate({**run_spec.model_dump(), **run_spec_overrides})


def _task_run_spec(
    *,
    resources: Optional[dict] = None,
    image: Optional[str] = None,
    docker: Optional[bool] = None,
    groups: Optional[list[dict]] = None,
) -> RunSpec:
    conf: dict[str, Any] = {"type": "task", "commands": ["echo hello"]}
    if groups is not None:
        conf.pop("commands", None)
        conf["groups"] = groups
    if resources is not None:
        conf["resources"] = resources
    if image is not None:
        conf["image"] = image
    if docker is not None:
        conf["docker"] = docker
    return get_run_spec(
        repo_id="test-repo",
        run_name="test-run",
        configuration=TaskConfiguration.model_validate(conf),
    )


def _service_run_spec(
    *,
    replicas: list[dict],
    resources: Optional[dict] = None,
    image: Optional[str] = None,
    docker: Optional[bool] = None,
) -> RunSpec:
    conf: dict[str, Any] = {"type": "service", "port": 8000, "replicas": replicas}
    if resources is not None:
        conf["resources"] = resources
    if image is not None:
        conf["image"] = image
    if docker is not None:
        conf["docker"] = docker
    return get_run_spec(
        repo_id="test-repo",
        run_name="test-run",
        configuration=ServiceConfiguration.model_validate(conf),
    )


def _validate(run_spec: RunSpec) -> None:
    validate_run_spec_and_set_defaults(SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec)


class TestValidateRunSpecRetryDuration:
    def test_model_accepts_negative_retry_duration_for_backward_compatibility(self):
        retry = ProfileRetry(duration=-1)

        assert retry.duration == -1

    def test_rejects_negative_retry_duration_for_new_run_specs(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            profile=Profile(name="default", retry=ProfileRetry(duration=-1)),
        )

        with pytest.raises(ServerClientError, match="retry.duration cannot be negative"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )


class TestValidateRunSpecGroupsIpRefs:
    def test_rejects_typo_groups_ref_in_node_group_commands(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(
                image="debian",
                groups=[
                    NodeGroup(
                        name="head",
                        nodes=1,
                        commands=["echo ${{ groups[0].nodes[0].IP }}"],
                    ),
                ],
            ),
        )

        with pytest.raises(ServerClientError, match="Illegal reference name"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )

    def test_accepts_valid_groups_ref(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(
                image="debian",
                groups=[
                    NodeGroup(
                        name="head",
                        nodes=1,
                        commands=["echo ${{ groups[0].nodes[0].IP_ADDRESS }}"],
                    ),
                ],
            ),
        )

        validate_run_spec_and_set_defaults(
            SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
        )

    def test_rejects_groups_ref_in_env(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(
                image="debian",
                commands=["echo ok"],
                env={"PREFILL_URL": "http://${{ groups[1].nodes[0].IP_ADDRESS }}"},
            ),
        )

        with pytest.raises(ServerClientError, match="only supported in commands, not in `env`"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )

    def test_rejects_out_of_range_group_index(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(
                image="debian",
                groups=[
                    NodeGroup(
                        name="head",
                        nodes=1,
                        commands=["echo ${{ groups[1].nodes[0].IP_ADDRESS }}"],
                    ),
                ],
            ),
        )

        with pytest.raises(ServerClientError, match="out of range"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )

    def test_rejects_out_of_range_node_index(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(
                image="debian",
                groups=[
                    NodeGroup(
                        name="head",
                        nodes=1,
                        commands=["echo ${{ groups[0].nodes[1].IP_ADDRESS }}"],
                    ),
                ],
            ),
        )

        with pytest.raises(ServerClientError, match="out of range"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )

    def test_rejects_replicas_member_in_task_commands(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(
                image="debian",
                groups=[
                    NodeGroup(
                        name="head",
                        nodes=1,
                        commands=["echo ${{ groups[0].replicas[0].IP_ADDRESS }}"],
                    ),
                ],
            ),
        )

        with pytest.raises(ServerClientError, match="Illegal reference name"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )

    def test_rejects_nodes_member_in_service_commands(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=ServiceConfiguration.model_validate(
                {
                    "type": "service",
                    "port": 8000,
                    "image": "debian",
                    "groups": [
                        {
                            "replicas": 1,
                            "commands": ["echo ${{ groups[0].nodes[0].IP_ADDRESS }}"],
                        }
                    ],
                }
            ),
        )

        with pytest.raises(ServerClientError, match="Illegal reference name"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )

    def test_accepts_service_replicas_ref_on_fixed_and_min_slot(self):
        for replicas in (1, "1..4"):
            group = {
                "replicas": replicas,
                "commands": ["echo ${{ groups[0].replicas[0].IP_ADDRESS }}"],
            }
            if replicas == "1..4":
                group["scaling"] = {"metric": "rps", "target": 10}
            run_spec = get_run_spec(
                repo_id="test-repo",
                configuration=_service_with_groups([group]),
            )
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )

    def test_accepts_service_replicas_indexes_for_fixed_count(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=_service_with_groups(
                [
                    {
                        "replicas": 2,
                        "commands": [
                            "echo ${{ groups[0].replicas[0].IP_ADDRESS }} "
                            "${{ groups[0].replicas[1].IP_ADDRESS }}"
                        ],
                    }
                ]
            ),
        )
        validate_run_spec_and_set_defaults(
            SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
        )

    def test_rejects_service_replicas_index_above_min(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=_service_with_groups(
                [
                    {
                        "replicas": "1..4",
                        "scaling": {"metric": "rps", "target": 10},
                        "commands": ["echo ${{ groups[0].replicas[1].IP_ADDRESS }}"],
                    }
                ]
            ),
        )

        with pytest.raises(ServerClientError, match="out of range"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )

    def test_rejects_service_replicas_ref_into_scale_to_zero_group(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=_service_with_groups(
                [
                    {
                        "replicas": "0..4",
                        "scaling": {"metric": "rps", "target": 10},
                        "commands": ["echo ${{ groups[0].replicas[0].IP_ADDRESS }}"],
                    }
                ]
            ),
        )

        with pytest.raises(ServerClientError, match="scales to zero"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )

    def test_rejects_service_replicas_group_out_of_range(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=_service_with_groups(
                [
                    {
                        "replicas": 1,
                        "commands": ["echo ${{ groups[7].replicas[9].IP_ADDRESS }}"],
                    }
                ]
            ),
        )

        with pytest.raises(ServerClientError, match="out of range"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )

    def test_accepts_service_ref_to_another_group_min_slot(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=_service_with_groups(
                [
                    {
                        "replicas": 1,
                        "commands": [
                            "smg --prefill http://${{ groups[1].replicas[0].IP_ADDRESS }}:8000"
                        ],
                    },
                    {
                        "replicas": 1,
                        "commands": ["echo prefill"],
                    },
                ]
            ),
        )
        validate_run_spec_and_set_defaults(
            SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
        )

    def test_rejects_service_groups_ref_in_env(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=ServiceConfiguration.model_validate(
                {
                    "type": "service",
                    "port": 8000,
                    "image": "debian",
                    "commands": ["echo ok"],
                    "env": {
                        "PREFILL_URL": "http://${{ groups[1].replicas[0].IP_ADDRESS }}",
                    },
                }
            ),
        )

        with pytest.raises(ServerClientError, match="only supported in commands, not in `env`"):
            validate_run_spec_and_set_defaults(
                SimpleNamespace(ssh_public_key="ssh-rsa test"), run_spec
            )


class TestRunSpecHasReplicaIpRefs:
    def test_true_when_service_group_command_has_replica_ref(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=_service_with_groups(
                [
                    {"replicas": 1, "commands": ["echo router"]},
                    {
                        "replicas": 1,
                        "commands": ["echo ${{ groups[0].replicas[0].IP_ADDRESS }}"],
                    },
                ]
            ),
        )
        assert run_spec_has_replica_ip_refs(run_spec)

    def test_false_when_service_has_no_replica_refs(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=_service_with_groups(
                [{"replicas": 1, "commands": ["echo ok"]}],
            ),
        )
        assert not run_spec_has_replica_ip_refs(run_spec)

    def test_false_for_task_node_refs(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(
                image="debian",
                groups=[
                    NodeGroup(
                        name="head",
                        nodes=1,
                        commands=["echo ${{ groups[0].nodes[0].IP_ADDRESS }}"],
                    ),
                ],
            ),
        )
        assert not run_spec_has_replica_ip_refs(run_spec)


class TestCheckCanUpdateConfigurationRouterType:
    def test_sglang_to_dynamo_router_type_change_is_rejected(self):
        current = _run_spec(_service_configuration(router_type="sglang"))
        new = _run_spec(_service_configuration(router_type="dynamo"))
        with pytest.raises(ServerClientError, match="router.type"):
            check_can_update_run_spec(current, new)

    def test_dynamo_to_sglang_router_type_change_is_rejected(self):
        current = _run_spec(_service_configuration(router_type="dynamo"))
        new = _run_spec(_service_configuration(router_type="sglang"))
        with pytest.raises(ServerClientError, match="router.type"):
            check_can_update_run_spec(current, new)

    def test_same_router_type_no_other_changes_succeeds(self):
        current = _run_spec(_service_configuration(router_type="dynamo"))
        new = _run_spec(_service_configuration(router_type="dynamo"))
        check_can_update_run_spec(current, new)


class TestCheckCanUpdateConfigurationDynamoRouterGroup:
    def test_dynamo_router_group_commands_change_is_rejected(self):
        current = _run_spec(_service_configuration(router_type="dynamo", router_commands="a"))
        new = _run_spec(_service_configuration(router_type="dynamo", router_commands="b"))
        with pytest.raises(ServerClientError, match="Dynamo router replica group"):
            check_can_update_run_spec(current, new)


class TestCheckCanUpdateConfigurationDynamoTopLevel:
    def test_dynamo_top_level_image_change_is_rejected(self):
        current = _run_spec(_service_configuration(router_type="dynamo", image="img:1"))
        new = _run_spec(_service_configuration(router_type="dynamo", image="img:2"))
        with pytest.raises(ServerClientError, match="image.*Dynamo"):
            check_can_update_run_spec(current, new)

    def test_dynamo_top_level_env_change_is_rejected(self):
        current = _run_spec(_service_configuration(router_type="dynamo", env={"FOO": "1"}))
        new = _run_spec(_service_configuration(router_type="dynamo", env={"FOO": "2"}))
        with pytest.raises(ServerClientError, match="env.*Dynamo"):
            check_can_update_run_spec(current, new)


class TestCheckCanUpdateRunSpecDynamoSpecLevel:
    @pytest.mark.parametrize(
        ("field", "current_overrides", "new_overrides"),
        [
            pytest.param(
                "repo_code_hash",
                {"repo_code_hash": "hash-a"},
                {"repo_code_hash": "hash-b"},
                id="repo_code_hash",
            ),
            pytest.param(
                "repo_data",
                {"repo_data": LocalRunRepoData(repo_dir="/repo/a")},
                {"repo_data": LocalRunRepoData(repo_dir="/repo/b")},
                id="repo_data",
            ),
            pytest.param(
                "file_archives",
                {
                    "file_archives": [
                        FileArchiveMapping(
                            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                            path="/work/a.txt",
                        ),
                    ],
                },
                {
                    "file_archives": [
                        FileArchiveMapping(
                            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                            path="/work/b.txt",
                        ),
                    ],
                },
                id="file_archives",
            ),
            pytest.param(
                "working_dir",
                {"working_dir": "/old-top"},
                {"working_dir": "/new-top"},
                id="working_dir",
            ),
        ],
    )
    def test_dynamo_spec_level_field_change_is_rejected(
        self, field: str, current_overrides: dict, new_overrides: dict
    ) -> None:
        cfg = _service_configuration(router_type="dynamo")
        current = _run_spec_with_overrides(cfg, **current_overrides)
        new = _run_spec_with_overrides(cfg, **new_overrides)

        with pytest.raises(ServerClientError, match=re.escape(field)):
            check_can_update_run_spec(current, new)


class TestCheckCanUpdateConfigurationWorkerOnlyChangesAllowed:
    def test_dynamo_worker_count_min_change_is_allowed(self):
        current = _run_spec(_service_configuration(router_type="dynamo", worker_count_min=1))
        new = _run_spec(_service_configuration(router_type="dynamo", worker_count_min=2))
        # Worker group count change is allowed on a Dynamo service.
        check_can_update_run_spec(current, new)

    def test_dynamo_worker_commands_change_is_allowed(self):
        current = _run_spec(_service_configuration(router_type="dynamo", worker_commands="x"))
        new = _run_spec(_service_configuration(router_type="dynamo", worker_commands="y"))
        # Non-router replica group's commands change is allowed.
        check_can_update_run_spec(current, new)


class TestCheckCanUpdateConfigurationNonDynamoUnchanged:
    def test_sglang_top_level_image_change_is_allowed(self):
        current = _run_spec(_service_configuration(router_type="sglang", image="img:1"))
        new = _run_spec(_service_configuration(router_type="sglang", image="img:2"))
        # Top-level changes on SGLang services flow through to the existing
        # rolling-deployment path; no Dynamo gate fires.
        check_can_update_run_spec(current, new)

    def test_no_router_top_level_image_change_is_allowed(self):
        current = _run_spec(_service_configuration(router_type=None, image="img:1"))
        new = _run_spec(_service_configuration(router_type=None, image="img:2"))
        check_can_update_run_spec(current, new)


class TestCheckCanUpdateConfigurationFieldAllowlist:
    """`_check_can_update_configuration` is also called directly with configs only."""

    def test_non_dynamo_image_change_passes_configuration_gate(self):
        current = _service_configuration(router_type="sglang", image="img:1")
        new = _service_configuration(router_type="sglang", image="img:2")
        _check_can_update_configuration(current, new, ignore_files=True)


class TestCheckCanUpdateRunSpecResources:
    """Non-service configurations cannot be redeployed, so only compatible changes are allowed."""

    def test_allows_relaxing_cpu_arch(self):
        # Older servers always resolved `cpu.arch`, so re-applying an unchanged configuration
        # after a server upgrade must not be rejected
        current = _task_run_spec(resources={"cpu": "x86:2"}, image="ubuntu")
        new = _task_run_spec(resources={"cpu": 2}, image="ubuntu")

        check_can_update_run_spec(current, new)

    def test_allows_unchanged_resources(self):
        current = _task_run_spec(resources={"cpu": "x86:2"}, image="ubuntu")
        new = _task_run_spec(resources={"cpu": "x86:2"}, image="ubuntu")

        check_can_update_run_spec(current, new)

    def test_rejects_setting_cpu_arch(self):
        current = _task_run_spec(resources={"cpu": 2}, image="ubuntu")
        new = _task_run_spec(resources={"cpu": "x86:2"}, image="ubuntu")

        with pytest.raises(ServerClientError, match="resources"):
            check_can_update_run_spec(current, new)

    def test_rejects_changing_cpu_arch(self):
        current = _task_run_spec(resources={"cpu": "x86:2"}, image="ubuntu")
        new = _task_run_spec(resources={"cpu": "arm:2"}, image="ubuntu")

        with pytest.raises(ServerClientError, match="resources"):
            check_can_update_run_spec(current, new)

    def test_rejects_changing_cpu_count(self):
        current = _task_run_spec(resources={"cpu": "x86:2"}, image="ubuntu")
        new = _task_run_spec(resources={"cpu": 4}, image="ubuntu")

        with pytest.raises(ServerClientError, match="resources"):
            check_can_update_run_spec(current, new)

    def test_rejects_changing_other_resources(self):
        current = _task_run_spec(resources={"cpu": "x86:2", "memory": "8GB"}, image="ubuntu")
        new = _task_run_spec(resources={"cpu": 2, "memory": "16GB"}, image="ubuntu")

        with pytest.raises(ServerClientError, match="resources"):
            check_can_update_run_spec(current, new)


class TestSetRunSpecResourcesDefaultsGpuVendor:
    @pytest.mark.parametrize(
        ["gpu_spec", "expected_vendor"],
        [
            ("A100", gpuhunt.AcceleratorVendor.NVIDIA),
            ("a40,l40", gpuhunt.AcceleratorVendor.NVIDIA),  # different names, same vendor
            ("Mi300X", gpuhunt.AcceleratorVendor.AMD),
            ("Gaudi2", gpuhunt.AcceleratorVendor.INTEL),
            ("n300", gpuhunt.AcceleratorVendor.TENSTORRENT),
            ("v5litepod-8", gpuhunt.AcceleratorVendor.GOOGLE),
        ],
    )
    def test_sets_vendor_detected_by_gpu_names(
        self, gpu_spec: str, expected_vendor: gpuhunt.AcceleratorVendor
    ):
        run_spec = _task_run_spec(resources={"gpu": gpu_spec}, image="ubuntu")

        set_run_spec_resources_defaults(run_spec)

        assert run_spec.configuration.resources.gpu.vendor == expected_vendor

    @pytest.mark.parametrize(
        "gpu_spec",
        [
            "UNKNOWN1000",  # an unknown name
            "A100,UNKNOWN1000",  # known and unknown names
            "A100,MI300X",  # names of different vendors
        ],
    )
    def test_does_not_set_vendor_if_gpu_names_are_ambiguous(self, gpu_spec: str):
        run_spec = _task_run_spec(resources={"gpu": gpu_spec}, image="ubuntu")

        set_run_spec_resources_defaults(run_spec)

        assert run_spec.configuration.resources.gpu.vendor is None

    def test_does_not_override_vendor_set_by_the_user(self):
        run_spec = _task_run_spec(
            resources={"gpu": {"vendor": "amd", "name": ["A100"]}}, image="ubuntu"
        )

        set_run_spec_resources_defaults(run_spec)

        assert run_spec.configuration.resources.gpu.vendor == gpuhunt.AcceleratorVendor.AMD

    def test_sets_nvidia_if_the_default_image_is_used(self):
        run_spec = _task_run_spec(resources={"gpu": "1"})

        set_run_spec_resources_defaults(run_spec)

        assert run_spec.configuration.resources.gpu.vendor == gpuhunt.AcceleratorVendor.NVIDIA

    @pytest.mark.parametrize(
        ["image", "docker"],
        [
            ("ubuntu", None),
            (None, True),  # the DinD image can run containers with any accelerator
        ],
    )
    def test_does_not_set_vendor_if_the_default_image_is_not_used(
        self, image: Optional[str], docker: Optional[bool]
    ):
        run_spec = _task_run_spec(resources={"gpu": "1"}, image=image, docker=docker)

        set_run_spec_resources_defaults(run_spec)

        assert run_spec.configuration.resources.gpu.vendor is None

    def test_does_not_set_vendor_if_no_gpu_requested(self):
        run_spec = _task_run_spec(resources={"gpu": "0"})

        set_run_spec_resources_defaults(run_spec)

        assert run_spec.configuration.resources.gpu.vendor is None

    def test_sets_default_gpu_spec_if_gpu_is_null(self):
        run_spec = _task_run_spec(resources={"gpu": None})

        set_run_spec_resources_defaults(run_spec)

        gpu_spec = run_spec.configuration.resources.gpu
        assert gpu_spec is not None
        assert gpu_spec.name is None
        assert gpu_spec.count.min == 0
        assert gpu_spec.count.max is None
        assert gpu_spec.vendor == gpuhunt.AcceleratorVendor.NVIDIA


class TestSetRunSpecResourcesDefaultsReplicaGroups:
    def test_sets_defaults_for_every_replica_group(self):
        run_spec = _service_run_spec(
            replicas=[
                {"count": 1, "commands": ["echo"], "resources": {"gpu": "MI300X"}},
                {"count": 1, "commands": ["echo"], "resources": {"gpu": "GH200"}},
                {"count": 1, "commands": ["echo"]},
            ],
        )

        set_run_spec_resources_defaults(run_spec)

        groups = run_spec.configuration.groups
        assert groups is not None
        assert [g.resources.gpu.vendor for g in groups] == [
            gpuhunt.AcceleratorVendor.AMD,
            gpuhunt.AcceleratorVendor.NVIDIA,
            gpuhunt.AcceleratorVendor.NVIDIA,
        ]

    @pytest.mark.parametrize(
        ["service_image", "group_image", "expected_vendor"],
        [
            (None, None, gpuhunt.AcceleratorVendor.NVIDIA),
            (None, "ubuntu", None),  # the group image overrides the default image
            ("ubuntu", None, None),  # the group inherits the service-level image
        ],
    )
    def test_infers_vendor_from_the_image_used_by_the_group(
        self,
        service_image: Optional[str],
        group_image: Optional[str],
        expected_vendor: Optional[gpuhunt.AcceleratorVendor],
    ):
        group: dict = {"count": 1, "commands": ["echo"], "resources": {"gpu": "1"}}
        if group_image is not None:
            group["image"] = group_image
        run_spec = _service_run_spec(replicas=[group], image=service_image)

        set_run_spec_resources_defaults(run_spec)

        assert run_spec.configuration.groups is not None
        assert run_spec.configuration.groups[0].resources.gpu.vendor == expected_vendor

    def test_sets_defaults_for_top_level_resources(self):
        # The top-level resources are ignored when replica groups are set, but they are still
        # normalized so that resubmitting the same configuration produces no spec diff
        run_spec = _service_run_spec(
            replicas=[{"count": 1, "commands": ["echo"]}],
            resources={"gpu": "H100"},
        )

        set_run_spec_resources_defaults(run_spec)

        resources = run_spec.configuration.resources
        assert resources.gpu.vendor == gpuhunt.AcceleratorVendor.NVIDIA


class TestSetRunSpecResourcesDefaultsNodeGroups:
    def test_sets_defaults_for_every_node_group(self):
        run_spec = _task_run_spec(
            groups=[
                {"nodes": 1, "commands": ["echo"], "resources": {"gpu": "MI300X"}},
                {"nodes": 1, "commands": ["echo"], "resources": {"gpu": "GH200"}},
                {"nodes": 1, "commands": ["echo"]},
            ],
        )

        set_run_spec_resources_defaults(run_spec)

        groups = run_spec.configuration.node_groups
        assert [g.resources.gpu.vendor for g in groups] == [
            gpuhunt.AcceleratorVendor.AMD,
            gpuhunt.AcceleratorVendor.NVIDIA,
            gpuhunt.AcceleratorVendor.NVIDIA,
        ]

    def test_sets_defaults_for_top_level_resources(self):
        # Top-level resources are unused when node groups are set, but still normalized
        # so resubmitting the same configuration produces no spec diff.
        run_spec = _task_run_spec(
            groups=[{"nodes": 1, "commands": ["echo"]}],
            resources={"gpu": "H100"},
        )

        set_run_spec_resources_defaults(run_spec)

        resources = run_spec.configuration.resources
        assert resources.gpu.vendor == gpuhunt.AcceleratorVendor.NVIDIA


class TestValidateRunSpecGpuVendorAndImage:
    UNSUPPORTED_GPU_SPECS = ["amd", "MI300X", "intel", "Gaudi2", "tenstorrent", "n300"]

    @pytest.mark.parametrize("gpu_spec", UNSUPPORTED_GPU_SPECS)
    def test_rejects_gpu_not_supported_by_the_default_image(self, gpu_spec: str):
        run_spec = _task_run_spec(resources={"gpu": gpu_spec})

        with pytest.raises(ServerClientError, match="`image` must be set"):
            _validate(run_spec)

    @pytest.mark.parametrize("gpu_spec", UNSUPPORTED_GPU_SPECS)
    @pytest.mark.parametrize(["image", "docker"], [("rocm", None), (None, True)])
    def test_allows_any_gpu_if_the_default_image_is_not_used(
        self, gpu_spec: str, image: Optional[str], docker: Optional[bool]
    ):
        _validate(_task_run_spec(resources={"gpu": gpu_spec}, image=image, docker=docker))

    @pytest.mark.parametrize(
        "gpu_spec",
        [
            "nvidia",
            "H100",
            # TPU workloads install all dependencies from PyPI, so they work with the default image
            "google",
            "v5litepod-8",
            "UNKNOWN1000",  # unknown names are not validated
        ],
    )
    def test_allows_gpu_supported_by_the_default_image(self, gpu_spec: str):
        _validate(_task_run_spec(resources={"gpu": gpu_spec}))

    def test_allows_any_vendor_if_no_gpu_requested(self):
        _validate(_task_run_spec(resources={"gpu": {"vendor": "amd", "count": 0}}))

    def test_reports_replica_groups_requiring_image(self):
        run_spec = _service_run_spec(
            replicas=[
                {"count": 1, "commands": ["echo"], "resources": {"gpu": "MI300X"}},
                {"count": 1, "commands": ["echo"], "resources": {"gpu": "H100"}},
                {"count": 1, "commands": ["echo"], "resources": {"gpu": "n300"}},
            ],
        )

        with pytest.raises(ServerClientError, match=re.escape("groups[0, 2]")):
            _validate(run_spec)

    def test_allows_replica_group_with_its_own_image(self):
        run_spec = _service_run_spec(
            replicas=[{"count": 1, "image": "rocm", "resources": {"gpu": "MI300X"}}],
        )

        _validate(run_spec)

    def test_reports_node_groups_requiring_image(self):
        run_spec = _task_run_spec(
            groups=[
                {"nodes": 1, "commands": ["echo"], "resources": {"gpu": "MI300X"}},
                {"nodes": 1, "commands": ["echo"], "resources": {"gpu": "H100"}},
                {"nodes": 1, "commands": ["echo"], "resources": {"gpu": "n300"}},
            ],
        )

        with pytest.raises(ServerClientError, match=re.escape("groups[0, 2]")):
            _validate(run_spec)

    def test_allows_node_group_with_task_level_image(self):
        run_spec = _task_run_spec(
            groups=[{"nodes": 1, "commands": ["echo"], "resources": {"gpu": "MI300X"}}],
            image="rocm",
        )

        _validate(run_spec)


class TestValidateRunSpecCpuArchAndImage:
    # NOTE: only an explicitly requested ARM arch is validated. The arch is not inferred from
    # the GPU name, as the actual arch is only known once an offer is selected -- the same
    # fleet may provide both ARM (e.g., GH200) and x86 (e.g., H200) instances.
    def test_rejects_arm_without_image(self):
        with pytest.raises(ServerClientError, match="`image` must be set when ARM CPU requested"):
            _validate(_task_run_spec(resources={"cpu": "arm:2"}))

    def test_allows_arm_gpu_without_image(self):
        # The run gets `arch: x86` requirements (the default image is x86-only) and is expected
        # to find no offers rather than to be rejected
        _validate(_task_run_spec(resources={"gpu": "GH200"}))

    def test_allows_arm_with_image(self):
        _validate(_task_run_spec(resources={"cpu": "arm:2"}, image="ubuntu"))

    def test_rejects_arm_with_dind(self):
        # `image` cannot be set with `docker: true`, and the DinD image is x86-only
        with pytest.raises(ServerClientError, match="`docker: true` is not supported on ARM CPU"):
            _validate(_task_run_spec(resources={"cpu": "arm:2"}, docker=True))

    @pytest.mark.parametrize("resources", [None, {"cpu": "x86:2"}, {"gpu": "H100"}])
    def test_allows_x86_without_image(self, resources: Optional[dict]):
        _validate(_task_run_spec(resources=resources))

    def test_reports_replica_groups_requiring_image(self):
        run_spec = _service_run_spec(
            replicas=[
                {"count": 1, "commands": ["echo"], "resources": {"cpu": "arm:2"}},
                {"count": 1, "commands": ["echo"]},
                {"count": 1, "commands": ["echo"], "resources": {"cpu": "arm:4"}},
            ],
        )

        with pytest.raises(ServerClientError, match=re.escape("groups[0, 2]")):
            _validate(run_spec)

    def test_allows_replica_group_with_its_own_image(self):
        run_spec = _service_run_spec(
            replicas=[{"count": 1, "image": "ubuntu", "resources": {"cpu": "arm:2"}}],
        )

        _validate(run_spec)

    def test_reports_node_groups_requiring_image(self):
        run_spec = _task_run_spec(
            groups=[
                {"nodes": 1, "commands": ["echo"], "resources": {"cpu": "arm:2"}},
                {"nodes": 1, "commands": ["echo"]},
                {"nodes": 1, "commands": ["echo"], "resources": {"cpu": "arm:4"}},
            ],
        )

        with pytest.raises(ServerClientError, match=re.escape("groups[0, 2]")):
            _validate(run_spec)

    def test_allows_node_group_with_task_level_image(self):
        run_spec = _task_run_spec(
            groups=[{"nodes": 1, "commands": ["echo"], "resources": {"cpu": "arm:2"}}],
            image="ubuntu",
        )

        _validate(run_spec)
