import asyncio

from dstack._internal.cli.utils.common import console
from dstack._internal.cli.utils.run import print_run_plan
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.runs import JobPlan, RunPlan
from dstack._internal.server.services.jobs import get_jobs_from_run_spec
from dstack._internal.server.testing.common import get_run_spec

_OFFER_FLEET_HINT = (
    "Hint: Existing fleets are ignored, and all available offers are shown."
    " To filter by fleet, pass --fleet NAME."
)
_OFFER_FLEET_HINT_START = "Hint: Existing fleets are ignored"


def _get_offer(index: int) -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.AWS,
        instance=InstanceType(
            name=f"instance-{index}",
            resources=Resources(cpus=2, memory_mib=8192, spot=False, gpus=[]),
        ),
        region="us-east-1",
        price=float(index),
        availability=InstanceAvailability.AVAILABLE,
    )


def _get_run_plan(*, offers: list[InstanceOfferWithAvailability], total_offers: int) -> RunPlan:
    run_spec = get_run_spec(repo_id="test-repo")
    loop = asyncio.new_event_loop()
    try:
        job = loop.run_until_complete(
            get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)
        )[0]
    finally:
        loop.close()
    return RunPlan(
        project_name="test-project",
        user="test-user",
        run_spec=run_spec,
        effective_run_spec=run_spec,
        job_plans=[
            JobPlan(
                job_spec=job.job_spec,
                offers=offers,
                total_offers=total_offers,
                max_price=max((offer.price for offer in offers), default=None),
            )
        ],
        action=ApplyAction.CREATE,
    )


class TestPrintRunPlanOfferHint:
    def test_prints_hint_before_short_offer_table(self):
        run_plan = _get_run_plan(offers=[_get_offer(1), _get_offer(2)], total_offers=2)

        with console.capture() as capture:
            print_run_plan(
                run_plan,
                include_run_properties=False,
                show_offer_fleet_hint=True,
            )

        output = capture.get()
        assert " ".join(_OFFER_FLEET_HINT.split()) in " ".join(output.split())
        assert output.index(_OFFER_FLEET_HINT_START) < output.index("1  aws (us-east-1)")

    def test_prints_hint_after_truncated_offer_table(self):
        offers = [_get_offer(index) for index in range(1, 4)]
        run_plan = _get_run_plan(offers=offers, total_offers=10)

        with console.capture() as capture:
            print_run_plan(
                run_plan,
                include_run_properties=False,
                show_offer_fleet_hint=True,
            )

        output = capture.get()
        shown_footer = "Shown 3 of 10 offers, $3max"
        assert shown_footer in output
        assert " ".join(_OFFER_FLEET_HINT.split()) in " ".join(output.split())
        assert output.index(shown_footer) < output.index(_OFFER_FLEET_HINT_START)
