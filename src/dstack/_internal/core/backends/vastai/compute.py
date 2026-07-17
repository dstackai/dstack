import time
from typing import List, Optional

import gpuhunt
from gpuhunt.providers.vastai import VastAIProvider
from typing_extensions import assert_never

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithFilteredOffersCached,
    generate_unique_instance_name_for_job,
    get_docker_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.base.profile_options import get_backend_profile_options
from dstack._internal.core.backends.vastai.api_client import (
    VastAIAPIClient,
    VastAICreateInstanceError,
    VastAIRateLimitError,
)
from dstack._internal.core.backends.vastai.models import VastAIConfig
from dstack._internal.core.backends.vastai.profile_options import (
    VASTAI_DEFAULT_MIN_RELIABILITY,
    VASTAI_DEFAULT_OFFER_ORDER,
    VastAIOfferOrder,
    VastAIProfileOptions,
)
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import ComputeError, NoCapacityError, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
)
from dstack._internal.core.models.placement import PlacementGroup
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

    def _make_catalog(self, options: VastAIProfileOptions) -> gpuhunt.Catalog:
        filters = {
            "direct_port_count": {"gte": 1},
            "reliability2": {
                "gte": options.min_reliability
                if options.min_reliability is not None
                else VASTAI_DEFAULT_MIN_RELIABILITY
            },
            "inet_down": {"gt": 128},
            "verified": {"eq": True},
            "cuda_max_good": {"gte": 12.8},
            "compute_cap": {"gte": 600},
        }
        if options.min_score is not None:
            filters["score"] = {"gte": options.min_score}
        match options.offer_order or VASTAI_DEFAULT_OFFER_ORDER:
            case VastAIOfferOrder.SCORE:
                order = [("score", "desc")]
            case VastAIOfferOrder.PRICE:
                # NOTE: dph_base is only one of the price components,
                # so we also sort by InstanceOffer.price later for accurate results.
                order = [("dph_base", "asc")]
            case other:
                assert_never(other)
        catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        catalog.add_provider(
            VastAIProvider(
                community_cloud=self.config.allow_community_cloud,
                extra_filters=filters,
                order=order,
            )
        )
        return catalog

    def get_offers_by_requirements(
        self, requirements: Requirements
    ) -> List[InstanceOfferWithAvailability]:
        vastai_options = (
            get_backend_profile_options(requirements.backend_options, VastAIProfileOptions)
            or VastAIProfileOptions()
        )
        offers = get_catalog_offers(
            backend=BackendType.VASTAI,
            locations=self.config.regions or None,
            requirements=requirements,
            catalog=self._make_catalog(vastai_options),
        )
        offers = [
            offer.with_availability(
                availability=InstanceAvailability.AVAILABLE,
                instance_runtime=InstanceRuntime.RUNNER,
            )
            for offer in offers
        ]
        if (vastai_options.offer_order or VASTAI_DEFAULT_OFFER_ORDER) == VastAIOfferOrder.PRICE:
            offers = sorted(offers, key=lambda o: o.price)
        return offers

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
        placement_group: Optional[PlacementGroup],
        requirements: Requirements,
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name_for_job(
            run, job, max_length=MAX_INSTANCE_NAME_LEN
        )
        assert run.run_spec.ssh_key_pub is not None
        commands = get_docker_commands(
            [run.run_spec.ssh_key_pub.strip(), project_ssh_public_key.strip()]
        )
        offer_backend_data: VastAIOfferBackendData = VastAIOfferBackendData.__response__.parse_obj(
            instance_offer.backend_data
        )
        bid = None
        if instance_offer.instance.resources.spot:
            if offer_backend_data.min_bid is None:
                raise ComputeError(
                    "VastAIOfferBackendData.min_bid is unexpectedly missing for a spot offer"
                )
            bid = offer_backend_data.min_bid
        try:
            instance_id = self.api_client.create_instance(
                instance_name=instance_name,
                bundle_id=instance_offer.instance.name,
                image_name=job.job_spec.image_name,
                onstart=" && ".join(commands),
                disk_size=round(instance_offer.instance.resources.disk.size_mib / 1024),
                registry_auth=job.job_spec.registry_auth,
                bid=bid,
            )
        except VastAICreateInstanceError as e:
            if e.created_instance_id is not None:
                _terminate_instance_with_rate_limit_retry(
                    self.api_client, e.created_instance_id, retries=4
                )
                logger.debug(
                    "Terminated Vast.ai instance %s that failed to start", e.created_instance_id
                )
            raise NoCapacityError(e.resp) from e
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=str(instance_id),
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
        try:
            resp = self.api_client.get_instance(provisioning_data.instance_id)
        except VastAIRateLimitError:
            logger.warning(
                "Reached Vast.ai rate limit when updating instance %s provisioning data",
                provisioning_data.instance_id,
            )
            return
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
            if (
                resp.get("cur_state")
                == resp.get("intended_status")
                == resp.get("next_state")
                == "stopped"
            ):
                # Can happen, among other cases, when a spot instance is outbid (interrupted)
                raise ProvisioningError(
                    "Vast.ai reports current and intended instance state as `stopped`"
                )


class VastAIOfferBackendData(CoreModel):
    min_bid: float | None = None


def _terminate_instance_with_rate_limit_retry(
    client: VastAIAPIClient, instance_id: int, retries: int
) -> bool:
    for attempt in range(retries):
        try:
            client.destroy_instance(instance_id)
            return True
        except VastAIRateLimitError:
            if attempt + 1 < retries:
                logger.warning(
                    "Hit rate limit when terminating Vast.ai instance %s. Attempt %s/%s",
                    instance_id,
                    attempt + 1,
                    retries,
                )
                time.sleep(attempt + 1)
        except BaseException as e:
            logger.error(
                "Failed to terminate Vast.ai instance %s. Terminate it manually to avoid accumulating charges. Error: %r",
                instance_id,
                e,
            )
            raise
    logger.error(
        "Failed to terminate Vast.ai instance %s after %s attempts hit rate limits. Terminate it manually to avoid accumulating charges",
        instance_id,
        retries,
    )
    return False
