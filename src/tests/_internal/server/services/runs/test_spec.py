import pytest

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.server.services.runs.spec import (
    _check_can_update_configuration,
)


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


class TestCheckCanUpdateConfigurationRouterType:
    def test_sglang_to_dynamo_router_type_change_is_rejected(self):
        current = _service_configuration(router_type="sglang")
        new = _service_configuration(router_type="dynamo")
        with pytest.raises(ServerClientError, match="router.type"):
            _check_can_update_configuration(current, new, ignore_files=True)

    def test_dynamo_to_sglang_router_type_change_is_rejected(self):
        current = _service_configuration(router_type="dynamo")
        new = _service_configuration(router_type="sglang")
        with pytest.raises(ServerClientError, match="router.type"):
            _check_can_update_configuration(current, new, ignore_files=True)

    def test_same_router_type_no_other_changes_succeeds(self):
        current = _service_configuration(router_type="dynamo")
        new = _service_configuration(router_type="dynamo")
        _check_can_update_configuration(current, new, ignore_files=True)


class TestCheckCanUpdateConfigurationDynamoRouterGroup:
    def test_dynamo_router_group_commands_change_is_rejected(self):
        current = _service_configuration(router_type="dynamo", router_commands="a")
        new = _service_configuration(router_type="dynamo", router_commands="b")
        with pytest.raises(ServerClientError, match="Dynamo router replica group"):
            _check_can_update_configuration(current, new, ignore_files=True)


class TestCheckCanUpdateConfigurationDynamoTopLevel:
    def test_dynamo_top_level_image_change_is_rejected(self):
        current = _service_configuration(router_type="dynamo", image="img:1")
        new = _service_configuration(router_type="dynamo", image="img:2")
        with pytest.raises(ServerClientError, match="image.*Dynamo"):
            _check_can_update_configuration(current, new, ignore_files=True)

    def test_dynamo_top_level_env_change_is_rejected(self):
        current = _service_configuration(router_type="dynamo", env={"FOO": "1"})
        new = _service_configuration(router_type="dynamo", env={"FOO": "2"})
        with pytest.raises(ServerClientError, match="env.*Dynamo"):
            _check_can_update_configuration(current, new, ignore_files=True)


class TestCheckCanUpdateConfigurationWorkerOnlyChangesAllowed:
    def test_dynamo_worker_count_min_change_is_allowed(self):
        current = _service_configuration(router_type="dynamo", worker_count_min=1)
        new = _service_configuration(router_type="dynamo", worker_count_min=2)
        # Worker group count change is allowed on a Dynamo service.
        _check_can_update_configuration(current, new, ignore_files=True)

    def test_dynamo_worker_commands_change_is_allowed(self):
        current = _service_configuration(router_type="dynamo", worker_commands="x")
        new = _service_configuration(router_type="dynamo", worker_commands="y")
        # Non-router replica group's commands change is allowed.
        _check_can_update_configuration(current, new, ignore_files=True)


class TestCheckCanUpdateConfigurationNonDynamoUnchanged:
    def test_sglang_top_level_image_change_is_allowed(self):
        current = _service_configuration(router_type="sglang", image="img:1")
        new = _service_configuration(router_type="sglang", image="img:2")
        # Top-level changes on SGLang services flow through to the existing
        # rolling-deployment path; no Dynamo gate fires.
        _check_can_update_configuration(current, new, ignore_files=True)

    def test_no_router_top_level_image_change_is_allowed(self):
        current = _service_configuration(router_type=None, image="img:1")
        new = _service_configuration(router_type=None, image="img:2")
        _check_can_update_configuration(current, new, ignore_files=True)
