from dstack._internal.cli.commands.offer import _print_offers_table
from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)

_FLEET_HINT = (
    "Hint: Existing fleets are ignored, and all available offers are shown."
    " To filter by fleet, pass --fleet NAME."
)
_FLEET_HINT_START = "Hint: Existing fleets are ignored"


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


def _get_max_price(offers: list[InstanceOfferWithAvailability]) -> float:
    return max((offer.price for offer in offers), default=0.0)


class TestPrintOffersTableFleetHint:
    def test_prints_hint_before_short_offer_table(self):
        offers = [_get_offer(1), _get_offer(2)]

        with console.capture() as capture:
            _print_offers_table(
                offers=offers,
                total_offers=2,
                max_price=_get_max_price(offers),
                show_fleet_hint=True,
            )

        output = capture.get()
        assert " ".join(_FLEET_HINT.split()) in " ".join(output.split())
        assert output.index(_FLEET_HINT_START) < output.index("1  aws (us-east-1)")

    def test_prints_hint_after_truncated_offer_table(self):
        offers = [_get_offer(index) for index in range(1, 4)]

        with console.capture() as capture:
            _print_offers_table(
                offers=offers,
                total_offers=10,
                max_price=_get_max_price(offers),
                show_fleet_hint=True,
            )

        output = capture.get()
        shown_footer = "Shown 3 of 10 offers, $3max"
        assert shown_footer in output
        assert " ".join(_FLEET_HINT.split()) in " ".join(output.split())
        assert output.index(shown_footer) < output.index(_FLEET_HINT_START)
