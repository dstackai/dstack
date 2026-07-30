"""
Serialization stability across every boundary that writes a payload somebody else reads.

Each model is serialized through the *production* path — there are four distinct ones, noted on
each registry below — and compared against a fixture generated under pydantic v1. On v1 these are
regression tests; on the v2 branch they are the compat assertion.

Nothing here may reference the duality API (`__request__` / `__response__`): these tests have to
run unchanged on both versions, and duality is gone in v2.

Disposable: this package is deleted once the v2 release is verified in prod, except for a curated
subset of the `db/` fixtures, which outlive it because stored rows do.

Registries and test classes follow the same surface order as `test_parsing.py`:
db, backend_config, backend_creds, backend_data, api_request, api_response, runner, gateway, proxy.
"""

import json
from typing import Any, Callable, Union

import gpuhunt
import pytest
from pydantic import BaseModel

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.fleets import FleetConfiguration, FleetNodesSpec
from dstack._internal.core.models.repos.remote import RemoteRunRepoData
from dstack._internal.core.models.resources import CPUSpec, Range, ResourcesSpec
from dstack._internal.core.models.volumes import RunpodVolumeConfiguration, VolumeSpec
from dstack._internal.server.utils.routers import CustomORJSONResponse
from tests._internal.pydantic_compat import backend_factories, factories
from tests._internal.pydantic_compat.compare import assert_matches_fixture, canonicalize

# Written to a `Text` column via `.json()`.
DB_BLOBS: dict[str, Callable[[], CoreModel]] = {
    "compute_group_provisioning_data": factories.compute_group_provisioning_data,
    "fleet_spec": factories.fleet_spec,
    "gateway_compute_configuration": factories.gateway_compute_configuration,
    "gateway_configuration": factories.gateway_configuration,
    "image_pull_progress": factories.image_pull_progress,
    "instance_configuration": factories.instance_configuration,
    "instance_offer": factories.instance_offer,
    "job_provisioning_data": factories.job_provisioning_data,
    "job_runtime_data": factories.job_runtime_data,
    "job_spec": factories.job_spec,
    "placement_group_configuration": factories.placement_group_configuration,
    "placement_group_provisioning_data": factories.placement_group_provisioning_data,
    "profile": factories.profile,
    "remote_connection_info": factories.remote_connection_info,
    "requirements": factories.requirements,
    "resources": factories.resources,
    "run_spec": factories.run_spec,
    "service_spec": factories.service_spec,
    "volume_attachment_data": factories.volume_attachment_data,
    "volume_configuration": factories.volume_configuration,
    "volume_provisioning_data": factories.volume_provisioning_data,
}

# The three backend `Text` columns, all written with `.json()`. Split by column rather than by
# backend so a fixture is the exact bytes of one column: `config` and `auth` are written and read
# separately, and only recombined into an `XConfig` after both have been decoded.
BACKEND_STORED_CONFIGS = backend_factories.BACKEND_STORED_CONFIGS
BACKEND_CREDS = backend_factories.BACKEND_CREDS
BACKEND_DATA = backend_factories.BACKEND_DATA

# Sent by the API client as a request body — `body=X.json()`, 40 call sites in `api/server/`.
# This is the new-CLI-against-old-server direction.
API_REQUESTS: dict[str, Callable[[], CoreModel]] = {
    "apply_fleet_plan_request": factories.apply_fleet_plan_request,
    "apply_gateway_plan_request": factories.apply_gateway_plan_request,
    "apply_run_plan_request": factories.apply_run_plan_request,
    "create_volume_request": factories.create_volume_request,
    "delete_fleets_request": factories.delete_fleets_request,
    "save_repo_creds_request": factories.save_repo_creds_request,
}

# Returned from a router via `CustomORJSONResponse` — orjson with a `default=` hook rather than
# `.json()`, so this path can drift away from the one above.
API_RESPONSES: dict[str, Callable[[], CoreModel]] = {
    "fleet": factories.fleet,
    "fleet_plan": factories.fleet_plan,
    "gateway": factories.gateway,
    "project": factories.project,
    "run_plan": factories.run_plan,
    "secret": factories.secret,
    "server_info": factories.server_info,
    "user_with_creds": factories.user_with_creds,
    "volume": factories.volume,
}

# Sent by the server to the runner (shim) as a request body, via `.json()`.
RUNNER_REQUESTS: dict[str, Callable[[], CoreModel]] = {
    "component_install_request": factories.component_install_request,
    "legacy_submit_body": factories.legacy_submit_body,
    "shutdown_request": factories.shutdown_request,
    "submit_body": factories.submit_body,
    "task_submit_request": factories.task_submit_request,
    "task_terminate_request": factories.task_terminate_request,
}

# Returned by the gateway to the server. The request direction is not model-driven — the server
# hand-builds those payloads — so it is covered on the parsing side instead.
GATEWAY_RESPONSES: dict[str, Callable[[], BaseModel]] = {
    "service_stats": factories.service_stats,
}

# Returned to the caller of the OpenAI-compatible API. A chunk is dumped one at a time into an SSE
# stream (`f"data:{chunk.json()}"` in `proxy/lib/routers/model_proxy.py`) rather than as a body,
# which makes it a fifth production dump path.
PROXY_RESPONSES: dict[str, Callable[[], CoreModel]] = {
    "chat_completions_chunk": factories.chat_completions_chunk,
    "models_response": factories.models_response,
}

# Forwarded upstream by the model proxy. Dumped with `exclude_unset=True`, matching
# `proxy/lib/services/model_proxy/clients/openai.py`, and encoded with stdlib json the way httpx
# does for a `json=` body — the fourth distinct dump path, and the only one where
# `__fields_set__` decides what goes on the wire.
PROXY_REQUESTS: dict[str, Callable[[], CoreModel]] = {
    "chat_completions_request": factories.chat_completions_request,
}


# Surface -> (models, the production call that serializes them). Keeping the dump here rather than
# inside each test matters because `test_parsing` re-serializes these same fixtures to check
# unknown-field tolerance: it has to use the identical path, or it compares orjson output against
# `.json()` output and fails for reasons that have nothing to do with parsing.
SURFACES: dict[str, tuple[dict[str, Callable[[], Any]], Callable[[Any], Union[bytes, str]]]] = {
    "db": (DB_BLOBS, lambda model: model.json()),
    "backend_config": (BACKEND_STORED_CONFIGS, lambda model: model.json()),
    "backend_creds": (BACKEND_CREDS, lambda model: model.json()),
    "backend_data": (BACKEND_DATA, lambda model: model.json()),
    "api_request": (API_REQUESTS, lambda model: model.json()),
    "api_response": (API_RESPONSES, lambda model: bytes(CustomORJSONResponse(model).body)),
    "runner": (RUNNER_REQUESTS, lambda model: model.json()),
    "gateway": (GATEWAY_RESPONSES, lambda model: model.json()),
    "proxy": (PROXY_REQUESTS, lambda model: json.dumps(model.dict(exclude_unset=True))),
    "proxy_response": (PROXY_RESPONSES, lambda model: model.json()),
}

_CASES = [(surface, name) for surface, (reg, _) in SURFACES.items() for name in sorted(reg)]


def serialize(surface: str, name: str) -> Union[bytes, str]:
    """Build the model for a case and serialize it the way production does."""
    registry, dump = SURFACES[surface]
    return dump(registry[name]())


class TestSerialization:
    @pytest.mark.parametrize(("surface", "name"), _CASES, ids=lambda v: str(v))
    def test_matches_fixture(self, surface, name, regen):
        assert_matches_fixture(
            f"serialization/{surface}", name, serialize(surface, name), regen=regen
        )


class TestFleetNodesTargetCompatHack:
    """
    Pins the #3066 old-client hack explicitly, not just via the fixture bytes.

    `FleetNodesSpec.dict()` drops `target` when it equals `min`. A fixture would catch the change
    but not explain it; naming the invariant gives the v2 `@model_serializer` rewrite something
    unambiguous to satisfy.

    Instances are built fresh here rather than reached out of `factories.fleet()`: the `nodes`
    default in `get_fleet_configuration` is a single shared `FleetNodesSpec`, so mutating one
    reached through the fixture corrupts every later caller in the session.
    """

    def test_target_is_omitted_when_it_equals_min(self):
        assert "target" not in FleetNodesSpec(min=1, target=1, max=1).dict()

    def test_target_is_kept_when_it_differs_from_min(self):
        assert FleetNodesSpec(min=1, target=5, max=5).dict()["target"] == 5

    @pytest.mark.parametrize(
        ("nodes", "expected"),
        [
            pytest.param(
                FleetNodesSpec(min=1, target=1, max=1),
                {"min": 1, "max": 1},
                id="target-equals-min",
            ),
            pytest.param(
                FleetNodesSpec(min=1, target=5, max=5),
                {"min": 1, "target": 5, "max": 5},
                id="target-differs-from-min",
            ),
        ],
    )
    def test_dict_and_json_apply_the_same_override(self, nodes, expected):
        assert nodes.dict() == expected
        assert json.loads(nodes.json()) == expected

    @pytest.mark.parametrize(
        ("nodes", "expected"),
        [
            pytest.param(
                FleetNodesSpec(min=1, target=1, max=1),
                {"min": 1, "max": 1},
                id="target-equals-min",
            ),
            pytest.param(
                FleetNodesSpec(min=1, target=5, max=5),
                {"min": 1, "target": 5, "max": 5},
                id="target-differs-from-min",
            ),
        ],
    )
    def test_override_is_applied_when_nested(self, nodes, expected):
        configuration = FleetConfiguration(nodes=nodes)

        assert configuration.dict()["nodes"] == expected
        assert json.loads(configuration.json())["nodes"] == expected

    def test_the_api_fixture_exercises_the_hack(self):
        nodes = factories.fleet().spec.configuration.nodes
        assert nodes is not None
        assert nodes.min == nodes.target, "fixture must hit the target == min branch"


class TestResourcesSpecCPUCompatHack:
    @pytest.mark.parametrize(
        ("arch", "expected"),
        [
            pytest.param(None, {"min": 2, "max": 8}, id="unspecified-architecture"),
            pytest.param(
                gpuhunt.CPUArchitecture.X86,
                {"min": 2, "max": 8},
                id="x86-architecture",
            ),
            pytest.param(
                gpuhunt.CPUArchitecture.ARM,
                {"arch": "arm", "count": {"min": 2, "max": 8}},
                id="arm-architecture",
            ),
        ],
    )
    def test_dict_and_json_apply_the_same_override(self, arch, expected):
        resources = ResourcesSpec(
            cpu=CPUSpec(arch=arch, count=Range[int](min=2, max=8)),
        )

        assert json.loads(resources.json())["cpu"] == expected
        # CoreModel.json() must call the overridden dict(); this assertion would expose a drift
        # even if only one of the two methods retained the compatibility rewrite.
        assert canonicalize(json.dumps(resources.dict()["cpu"])) == canonicalize(
            json.dumps(expected)
        )

    @pytest.mark.parametrize(
        ("arch", "expected"),
        [
            pytest.param(None, {"min": 2, "max": 8}, id="unspecified-architecture"),
            pytest.param(
                gpuhunt.CPUArchitecture.ARM,
                {"arch": "arm", "count": {"min": 2, "max": 8}},
                id="arm-architecture",
            ),
        ],
    )
    def test_override_is_applied_when_nested(self, arch, expected):
        configuration = TaskConfiguration(
            commands=["echo hi"],
            resources=ResourcesSpec(
                cpu=CPUSpec(arch=arch, count=Range[int](min=2, max=8)),
            ),
        )

        assert json.loads(configuration.json())["resources"]["cpu"] == expected
        assert canonicalize(json.dumps(configuration.dict()["resources"]["cpu"])) == canonicalize(
            json.dumps(expected)
        )


class TestFieldSerializationFilters:
    def test_submit_body_nested_field_includes_are_preserved(self):
        body = factories.submit_body().dict()

        assert set(body["run"]) == {"id", "run_spec"}
        assert set(body["run"]["run_spec"]) == {
            "run_name",
            "repo_id",
            "repo_data",
            "configuration",
            "configuration_path",
        }
        assert set(body["job_spec"]) == {
            "replica_num",
            "job_num",
            "jobs_per_replica",
            "user",
            "commands",
            "env",
            "single_branch",
            "max_duration",
            "ssh_key",
            "working_dir",
            "repo_data",
            "repo_dir",
            "repo_exists_action",
            "file_archives",
        }
        assert set(body["job_submission"]) == {"id"}

    def test_derived_merged_profile_is_excluded_from_dict_and_json(self):
        spec = factories.run_spec()
        assert spec.merged_profile is not None

        assert "merged_profile" not in spec.dict()
        assert "merged_profile" not in json.loads(spec.json())

    def test_remote_repo_diff_bytes_are_excluded_from_dict_and_json(self):
        repo = RemoteRunRepoData(repo_name="dstack", repo_diff=b"secret diff")
        assert repo.repo_diff == b"secret diff"

        assert "repo_diff" not in repo.dict()
        assert "repo_diff" not in json.loads(repo.json())

    def test_runpod_compatibility_availability_zone_is_excluded_directly_and_nested(self):
        configuration = RunpodVolumeConfiguration(
            name="cache",
            region="US-KS-2",
            size="100GB",
            availability_zone="legacy-zone",
        )
        assert configuration.availability_zone == "legacy-zone"

        assert "availability_zone" not in configuration.dict()
        assert "availability_zone" not in json.loads(configuration.json())

        spec = VolumeSpec(configuration=configuration)
        assert "availability_zone" not in spec.dict()["configuration"]
        assert "availability_zone" not in json.loads(spec.json())["configuration"]


class TestCustomORJSONResponseCompat:
    def test_response_uses_the_same_nested_serializer_overrides_as_model_json(self):
        configuration = FleetConfiguration(nodes=FleetNodesSpec(min=1, target=1, max=1))

        response_body = bytes(CustomORJSONResponse(configuration).body)

        assert canonicalize(response_body) == canonicalize(configuration.json())
        assert "target" not in json.loads(response_body)["nodes"]
