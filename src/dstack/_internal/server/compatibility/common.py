from typing import Optional

from packaging.version import Version

from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
)


def patch_offers_list(
    offers: list[InstanceOfferWithAvailability], client_version: Optional[Version]
) -> None:
    if client_version is None:
        return
    # CLIs prior to 0.20.4 incorrectly display the `no_balance` availability in the run/fleet plan
    if client_version < Version("0.20.4"):
        for offer in offers:
            if offer.availability == InstanceAvailability.NO_BALANCE:
                offer.availability = InstanceAvailability.NOT_AVAILABLE
