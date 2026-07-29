"""
Deterministic model instances for the comparison fixtures.

Every value is pinned — no `uuid4()`, no `now()` — so a fixture only changes when serialization
changes. Builds on `dstack._internal.server.testing.common` where a factory already exists, so
these stay in sync with the shapes the rest of the suite uses.
"""

import uuid
from datetime import datetime, timezone

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import DevEnvironmentConfiguration
from dstack._internal.core.models.fleets import Fleet, FleetStatus
from dstack._internal.core.models.instances import Instance, InstanceStatus
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import Memory, Range, ResourcesSpec
from dstack._internal.core.models.runs import JobProvisioningData, RunSpec
from dstack._internal.server.testing.common import (
    get_fleet_spec,
    get_job_provisioning_data,
    get_run_spec,
)

_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_CREATED_AT = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def job_provisioning_data() -> JobProvisioningData:
    """Stored in `JobModel.job_provisioning_data` and `InstanceModel.job_provisioning_data`."""
    return get_job_provisioning_data(
        dockerized=True,
        availability_zone="us-east-1a",
        gpu_count=1,
    )


def run_spec() -> RunSpec:
    """
    Stored in `RunModel.run_spec` — the largest blob, and the one carrying the type zoo.

    `max_duration`/`idle_duration` are `Duration` (an `int` subclass) and `resources` carries
    `Memory` and `Range[T]`, so this fixture pins how the custom types render. Those are the types
    whose `__get_validators__` → `__get_pydantic_core_schema__` port is riskiest.

    Values are given in their already-parsed form rather than as YAML shorthand (`"2h"`,
    `"16GB.."`): shorthand only type-checks because a `pre=True` validator widens the input, and
    pinning the *parse* side is the job of the parse fixtures, not these.
    """
    return get_run_spec(
        repo_id="test-repo",
        profile=Profile(name="default", max_duration=7200, idle_duration=300),
        configuration=DevEnvironmentConfiguration(
            ide="vscode",
            resources=ResourcesSpec(
                cpu=Range[int](min=2, max=8),
                memory=Range[Memory](min=Memory(16), max=None),
            ),
        ),
    )


def fleet() -> Fleet:
    """
    Returned by `/api/project/{name}/fleets/list` through `CustomORJSONResponse`.

    The default `FleetNodesSpec` has `target == min`, which is what makes `FleetNodesSpec.dict()`
    drop `target` — the old-client compat hack from #3066. That override becomes a
    `@model_serializer` in v2, so this fixture is the thing that proves the hack survived.
    """
    return Fleet(
        id=_ID,
        name="test-fleet",
        project_name="test-project",
        spec=get_fleet_spec(),
        created_at=_CREATED_AT,
        status=FleetStatus.ACTIVE,
        instances=[
            Instance(
                id=_ID,
                project_name="test-project",
                name="test-instance",
                instance_num=0,
                status=InstanceStatus.IDLE,
                created=_CREATED_AT,
                backend=BackendType.AWS,
                region="us-east-1",
            )
        ],
    )
