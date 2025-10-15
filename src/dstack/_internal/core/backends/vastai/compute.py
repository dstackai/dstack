from typing import List, Optional

import gpuhunt
from gpuhunt.providers.vastai import VastAIProvider

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithFilteredOffersCached,
    generate_unique_instance_name_for_job,
    get_docker_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.vastai.api_client import VastAIAPIClient
from dstack._internal.core.backends.vastai.models import VastAIConfig
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


# Undocumented but names of len 60 work
MAX_INSTANCE_NAME_LEN = 60


class VastAICompute(
    ComputeWithFilteredOffersCached,
    Compute,
):
    def __init__(self, config: VastAIConfig):
        super().__init__()
        self.config = config
        self.api_client = VastAIAPIClient(config.creds.api_key)
        self.catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self.catalog.add_provider(
            VastAIProvider(
                extra_filters={
                    "direct_port_count": {"gte": 1},
                    "reliability2": {"gte": 0.9},
                    "inet_down": {"gt": 128},
                    "verified": {"eq": True},
                    "cuda_max_good": {"gte": 12.8},
                    "compute_cap": {"gte": 600},
                }
            )
        )

    def get_offers_by_requirements(
        self, requirements: Requirements
    ) -> List[InstanceOfferWithAvailability]:
        def spot_filter(offer):
            return not offer.instance.resources.spot

        extra_filter = spot_filter

        configured_regions = self.config.regions or []
        if configured_regions:
            normalized_exact_regions = {
                r.strip() for r in configured_regions if isinstance(r, str) and r.strip()
            }
            iso_country_codes = {
                r.strip().upper()
                for r in configured_regions
                if isinstance(r, str) and len(r.strip()) == 2 and r.strip().isalpha()
            }

            def region_accepts(offer):
                region_value = (offer.region or "").strip()
                if not region_value:
                    return False
                if region_value in normalized_exact_regions:
                    return True
                if "," in region_value:
                    trailing_code = region_value.split(",")[-1].strip().upper()
                    if trailing_code in iso_country_codes:
                        return True
                if len(region_value) == 2 and region_value.isalpha() and region_value.upper() in iso_country_codes:
                    return True
                return False

            def combined_filter(offer):
                return spot_filter(offer) and region_accepts(offer)

            extra_filter = combined_filter

        offers = get_catalog_offers(
            backend=BackendType.VASTAI,
            requirements=requirements,
            # TODO(egor-s): spots currently not supported
            extra_filter=extra_filter,
            catalog=self.catalog,
        )
        offers = [
            InstanceOfferWithAvailability(
                **offer.dict(),
                availability=InstanceAvailability.AVAILABLE,
                instance_runtime=InstanceRuntime.RUNNER,
            )
            for offer in offers
        ]
        return offers

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name_for_job(
            run, job, max_length=MAX_INSTANCE_NAME_LEN
        )
        assert run.run_spec.ssh_key_pub is not None
        commands = get_docker_commands(
            [run.run_spec.ssh_key_pub.strip(), project_ssh_public_key.strip()]
        )
        resp = self.api_client.create_instance(
            instance_name=instance_name,
            bundle_id=instance_offer.instance.name,
            image_name=job.job_spec.image_name,
            onstart=" && ".join(commands),
            disk_size=round(instance_offer.instance.resources.disk.size_mib / 1024),
            registry_auth=job.job_spec.registry_auth,
        )
        instance_id = resp["new_contract"]
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_id,
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="root",
            ssh_port=None,
            dockerized=False,
            ssh_proxy=None,
            backend_data=None,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        self.api_client.destroy_instance(instance_id)

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        resp = self.api_client.get_instance(provisioning_data.instance_id)
        if resp is not None:
            if resp["actual_status"] == "running":
                provisioning_data.hostname = resp["public_ipaddr"].strip()
                provisioning_data.ssh_port = int(
                    resp["ports"][f"{DSTACK_RUNNER_SSH_PORT}/tcp"][0]["HostPort"]
                )
            if (
                resp["actual_status"] == "created"
                and ": OCI runtime create failed:" in resp["status_msg"]
            ):
                raise ProvisioningError(resp["status_msg"])
