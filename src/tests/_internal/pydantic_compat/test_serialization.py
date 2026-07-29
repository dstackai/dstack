"""
Serialization stability for DB blobs and API responses.

Each model is serialized through the *production* path — `.json()` for anything written to a
`Text` column, `CustomORJSONResponse` for anything returned from a router — and compared against a
fixture generated under pydantic v1. On v1 these are regression tests; on the v2 branch they are
the compat assertion.

Nothing here may reference the duality API (`__request__` / `__response__`): these tests have to
run unchanged on both versions, and duality is gone in v2.

Disposable: this package is deleted once the v2 release is verified in prod, except for a curated
subset of the `db/` fixtures, which outlive it because stored rows do.
"""

from typing import Callable

import pytest

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.fleets import FleetNodesSpec
from dstack._internal.server.utils.routers import CustomORJSONResponse
from tests._internal.pydantic_compat import factories
from tests._internal.pydantic_compat.compare import assert_matches_fixture

# Written to a `Text` column via `.json()`.
DB_BLOBS: dict[str, Callable[[], CoreModel]] = {
    "job_provisioning_data": factories.job_provisioning_data,
    "run_spec": factories.run_spec,
}

# Returned from a router via `CustomORJSONResponse`.
API_RESPONSES: dict[str, Callable[[], CoreModel]] = {
    "fleet": factories.fleet,
}

# Sent by the API client as a request body — `body=X.json()`, 40 call sites in `api/server/`.
# This is the new-CLI-against-old-server direction, which nothing else in the suite covers.
API_REQUESTS: dict[str, Callable[[], CoreModel]] = {
    "delete_fleets_request": factories.delete_fleets_request,
    "apply_fleet_plan_request": factories.apply_fleet_plan_request,
}


class TestDbBlobSerialization:
    @pytest.mark.parametrize("name", sorted(DB_BLOBS))
    def test_matches_fixture(self, name, regen):
        payload = DB_BLOBS[name]().json()
        assert_matches_fixture("serialization/db", name, payload, regen=regen)


class TestApiResponseSerialization:
    @pytest.mark.parametrize("name", sorted(API_RESPONSES))
    def test_matches_fixture(self, name, regen):
        # Response bodies go through orjson with a `default=` hook, not through `.json()`, so the
        # two paths can drift apart. Serialize the way the router does.
        payload = bytes(CustomORJSONResponse(API_RESPONSES[name]()).body)
        assert_matches_fixture("serialization/api_response", name, payload, regen=regen)


class TestApiRequestSerialization:
    @pytest.mark.parametrize("name", sorted(API_REQUESTS))
    def test_matches_fixture(self, name, regen):
        payload = API_REQUESTS[name]().json()
        assert_matches_fixture("serialization/api_request", name, payload, regen=regen)


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

    def test_the_api_fixture_exercises_the_hack(self):
        nodes = factories.fleet().spec.configuration.nodes
        assert nodes is not None
        assert nodes.min == nodes.target, "fixture must hit the target == min branch"
