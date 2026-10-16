import pytest
from google.auth.credentials import AnonymousCredentials
from gpuhunt import AcceleratorVendor, CatalogItem

from dstack._internal.core.backends.gcp.compute import GCPCompute
from dstack._internal.core.backends.gcp.models import GCPConfig, GCPDefaultCreds


class TestGetAllOffersWithAvailability:
    @pytest.mark.parametrize(
        "tpu_config", [{}, {"tpu": False}, {"tpu": True}], ids=["default", "disabled", "enabled"]
    )
    def test_returns_tpu_offers_only_if_enabled(self, mocker, tpu_config):
        mocker.patch(
            "dstack._internal.core.backends.gcp.auth.authenticate",
            return_value=(AnonymousCredentials(), None),
        )
        compute = GCPCompute(
            GCPConfig(
                project_id="test-project",
                regions=["us-central1"],
                creds=GCPDefaultCreds(),
                **tpu_config,
            )
        )
        mocker.patch.object(compute.regions_client, "list", return_value=[])
        items = [
            CatalogItem(
                provider="gcp",
                instance_name=name,
                location="us-central1-a",
                price=1.0,
                cpu=4,
                memory=16,
                gpu_count=int(vendor is not None),
                gpu_vendor=vendor,
                gpu_name=gpu_name,
                gpu_memory=16 if vendor is not None else None,
                spot=False,
                disk_size=None,
            )
            for name, vendor, gpu_name in [
                ("n2-standard-4", None, None),
                ("g2-standard-4", AcceleratorVendor.NVIDIA, "L4"),
                ("v5litepod-8", AcceleratorVendor.GOOGLE, "v5litepod-8"),
            ]
        ]
        mocker.patch("gpuhunt.default_catalog").return_value.query.return_value = items

        offers = compute.get_all_offers_with_availability(unallocated_resources=False)

        expected_names = ["n2-standard-4", "g2-standard-4"]
        if tpu_config.get("tpu"):
            expected_names.append("v5litepod-8")
        assert [offer.instance.name for offer in offers] == expected_names
