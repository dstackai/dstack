import re
import uuid
from types import SimpleNamespace

import pytest

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import (
    DevEnvironmentConfiguration,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.files import FileArchiveMapping
from dstack._internal.core.models.profiles import InstanceNameSelector, Profile, ProfileRetry
from dstack._internal.core.models.repos.local import LocalRunRepoData
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.services.runs.spec import (
    _check_can_update_configuration,
    check_can_update_run_spec,
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
    return ServiceConfiguration.parse_obj(data)


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
    return RunSpec.parse_obj({**run_spec.dict(), **run_spec_overrides})


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


class TestValidateRunSpecInstances:
    def _user(self):
        return SimpleNamespace(ssh_public_key="ssh-rsa test")

    def test_rejects_fewer_instances_than_nodes(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(commands=["echo"], nodes=2),
            profile=Profile(
                name="default",
                instances=[InstanceNameSelector(name="my-fleet-0")],
            ),
        )

        with pytest.raises(ServerClientError, match="instances"):
            validate_run_spec_and_set_defaults(self._user(), run_spec)

    def test_allows_matching_instances_and_nodes(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(commands=["echo"], nodes=2),
            profile=Profile(
                name="default",
                instances=[
                    InstanceNameSelector(name="my-fleet-0"),
                    InstanceNameSelector(name="my-fleet-1"),
                ],
            ),
        )

        validate_run_spec_and_set_defaults(self._user(), run_spec)

    def test_allows_single_node_with_instances(self):
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=DevEnvironmentConfiguration(ide="vscode"),
            profile=Profile(
                name="default",
                instances=[InstanceNameSelector(name="my-fleet-3")],
            ),
        )

        validate_run_spec_and_set_defaults(self._user(), run_spec)


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
