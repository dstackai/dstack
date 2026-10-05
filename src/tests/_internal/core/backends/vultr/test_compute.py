from gpuhunt.providers.vultr import API_URL

from dstack._internal.core.backends.vultr.compute import VultrCompute
from dstack._internal.core.backends.vultr.models import VultrConfig, VultrCreds
from dstack._internal.core.models.instances import InstanceAvailability


class TestGetAllOffersWithAvailability:
    def test_uses_backend_credentials_for_gpu_availability(self, requests_mock, monkeypatch):
        monkeypatch.setenv("VULTR_API_KEY", "environment-key")
        requests_mock.get(f"{API_URL}/plans-metal?per_page=500", json={"plans_metal": []})
        requests_mock.get(
            f"{API_URL}/plans?type=all&per_page=500",
            json={
                "plans": [
                    {
                        "id": "vc2-2c-4gb",
                        "type": "vc2",
                        "vcpu_count": 2,
                        "ram": 4096,
                        "disk": 80,
                        "hourly_cost": 0.027,
                        "locations": ["blr", "fra"],
                    },
                    {
                        "id": "vcg-a40-24c-120g-48vram",
                        "type": "vdm",
                        "vcpu_count": 24,
                        "ram": 122880,
                        "disk": 1400,
                        "hourly_cost": 1.712,
                        "deploy_ondemand": True,
                        "locations": [],
                    },
                ],
            },
        )
        requests_mock.get(
            f"{API_URL}/regions/blr/availability?type=vdm",
            request_headers={"Authorization": "Bearer backend-key"},
            json={
                "available_plans": ["vcg-a40-24c-120g-48vram"],
                "available_vpc_only_plans": [],
            },
        )
        compute = VultrCompute(
            VultrConfig(creds=VultrCreds(api_key="backend-key"), regions=["blr"])
        )

        offers = compute.get_all_offers_with_availability(unallocated_resources=False)

        assert [offer.instance.name for offer in offers] == [
            "vc2-2c-4gb",
            "vcg-a40-24c-120g-48vram",
        ]
        assert all(offer.region == "blr" for offer in offers)
        assert all(offer.availability == InstanceAvailability.AVAILABLE for offer in offers)
        cpu_offer, gpu_offer = offers
        assert cpu_offer.instance.resources.cpus == 2
        assert cpu_offer.instance.resources.memory_mib == 4 * 1024
        assert cpu_offer.instance.resources.gpus == []
        assert cpu_offer.price == 0.027
        assert gpu_offer.instance.resources.cpus == 24
        assert gpu_offer.instance.resources.memory_mib == 120 * 1024
        [gpu] = gpu_offer.instance.resources.gpus
        assert gpu.name == "A40"
        assert gpu.memory_mib == 48 * 1024
        assert gpu_offer.price == 1.712
