import pytest

from dstack._internal.core.backends.nebius import compute as compute_module
from dstack._internal.core.backends.nebius.compute import NebiusCompute
from dstack._internal.core.backends.nebius.models import (
    NebiusConfig,
    NebiusServiceAccountCreds,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceAvailability,
    InstanceOffer,
    InstanceType,
    Resources,
)


def make_compute() -> NebiusCompute:
    return NebiusCompute(
        NebiusConfig(
            creds=NebiusServiceAccountCreds(
                service_account_id="service-account-id",
                public_key_id="public-key-id",
                private_key_content="private-key",
            )
        )
    )


def make_offer(
    price: float, spot: bool, is_preemptible_flat_rate: bool, gpu_count: int = 8
) -> InstanceOffer:
    return InstanceOffer(
        backend=BackendType.NEBIUS,
        instance=InstanceType(
            name=f"gpu-h100-sxm {gpu_count}gpu-128vcpu-1600gb",
            resources=Resources(
                cpus=128,
                memory_mib=1600 * 1024,
                gpus=[Gpu(name="H100", memory_mib=80 * 1024)] * gpu_count,
                spot=spot,
            ),
        ),
        region="eu-north1",
        price=price,
        backend_data={
            "fabrics": ["fabric-2"],
            "is_preemptible_flat_rate": is_preemptible_flat_rate,
        },
    )


class TestGetAllOffersWithAvailability:
    @pytest.fixture(autouse=True)
    def _mock_region_to_project_id(self, mocker):
        mocker.patch.object(NebiusCompute, "_region_to_project_id", {"eu-north1": "project-id"})

    @pytest.mark.parametrize(
        ("price", "gpu_count", "expected_price"),
        [
            (1.23, 1, 1.23),
            (1.2, 1, 1.2),
            (1.2341, 1, 1.235),
            (1.2349, 1, 1.235),
            (1.2350001, 1, 1.236),
            (0.0001, 1, 0.001),
            (2.007, 1, 2.007),
            (9.84, 8, 9.84),
            (1.23, 8, 1.232),
            (1.2341, 0, 1.235),
        ],
    )
    def test_rounds_spot_price_up_to_3_decimal_places_per_gpu(
        self, mocker, price, gpu_count, expected_price
    ):
        mocker.patch.object(
            compute_module,
            "get_catalog_offers",
            return_value=[
                make_offer(price, spot=True, is_preemptible_flat_rate=False, gpu_count=gpu_count)
            ],
        )

        offers = make_compute().get_all_offers_with_availability(unallocated_resources=False)

        assert len(offers) == 1
        assert offers[0].price == expected_price
        assert offers[0].availability == InstanceAvailability.UNKNOWN

    def test_keeps_on_demand_price_as_is(self, mocker):
        mocker.patch.object(
            compute_module,
            "get_catalog_offers",
            return_value=[make_offer(1.2341, spot=False, is_preemptible_flat_rate=False)],
        )

        offers = make_compute().get_all_offers_with_availability(unallocated_resources=False)

        assert offers[0].price == 1.2341

    def test_keeps_flat_rate_spot_price_as_is(self, mocker):
        mocker.patch.object(
            compute_module,
            "get_catalog_offers",
            return_value=[make_offer(1.2341, spot=True, is_preemptible_flat_rate=True)],
        )

        offers = make_compute().get_all_offers_with_availability(unallocated_resources=False)

        assert offers[0].price == 1.2341
