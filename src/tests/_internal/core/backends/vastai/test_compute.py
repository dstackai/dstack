from unittest.mock import MagicMock, patch

from dstack._internal.core.backends.vastai.compute import VastAICompute
from dstack._internal.core.backends.vastai.models import VastAIConfig, VastAICreds
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements


def _config(community_cloud=None) -> VastAIConfig:
    return VastAIConfig(creds=VastAICreds(api_key="test"), community_cloud=community_cloud)


def _requirements() -> Requirements:
    return Requirements(resources=ResourcesSpec())


def _offer(
    *, spot: bool, price: float = 0.5, min_bid: float | None = None
) -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.VASTAI,
        instance=InstanceType(
            name="12345",
            resources=Resources(
                cpus=8,
                memory_mib=32 * 1024,
                gpus=[Gpu(name="RTX4090", memory_mib=24 * 1024)],
                spot=spot,
                disk=Disk(size_mib=100 * 1024),
            ),
        ),
        region="Hong Kong, HK",
        price=price,
        availability=InstanceAvailability.AVAILABLE,
        backend_data={
            **({"min_bid": min_bid} if min_bid is not None else {}),
        },
    )


def _run_job(compute: VastAICompute, offer: InstanceOfferWithAvailability):
    run = MagicMock()
    run.run_spec.ssh_key_pub = "ssh-rsa AAAA test"
    job = MagicMock()
    job.job_spec.image_name = "dstackai/base:latest"
    job.job_spec.registry_auth = None
    with (
        patch(
            "dstack._internal.core.backends.vastai.compute.generate_unique_instance_name_for_job",
            return_value="dstack-test",
        ),
        patch(
            "dstack._internal.core.backends.vastai.compute.get_docker_commands",
            return_value=["echo hi"],
        ),
    ):
        compute.run_job(
            run=run,
            job=job,
            instance_offer=offer,
            project_ssh_public_key="ssh-rsa BBBB project",
            project_ssh_private_key="private-key",
            volumes=[],
            placement_group=None,
            requirements=_requirements(),
        )


def test_vastai_compute_enables_community_cloud_by_default():
    with (
        patch("dstack._internal.core.backends.vastai.compute.VastAIProvider") as vast_provider_cls,
        patch("dstack._internal.core.backends.vastai.compute.gpuhunt.Catalog") as catalog_cls,
        patch("dstack._internal.core.backends.vastai.compute.get_catalog_offers", return_value=[]),
    ):
        catalog_instance = catalog_cls.return_value
        compute = VastAICompute(_config())
        list(compute.get_offers(_requirements(), False))
        vast_provider_cls.assert_called_once()
        assert vast_provider_cls.call_args.kwargs["community_cloud"] is True
        catalog_instance.add_provider.assert_called_once()


def test_vastai_compute_can_enable_community_cloud():
    with (
        patch("dstack._internal.core.backends.vastai.compute.VastAIProvider") as vast_provider_cls,
        patch("dstack._internal.core.backends.vastai.compute.gpuhunt.Catalog") as catalog_cls,
        patch("dstack._internal.core.backends.vastai.compute.get_catalog_offers", return_value=[]),
    ):
        catalog_instance = catalog_cls.return_value
        compute = VastAICompute(_config(community_cloud=True))
        list(compute.get_offers(_requirements(), False))
        vast_provider_cls.assert_called_once()
        assert vast_provider_cls.call_args.kwargs["community_cloud"] is True
        catalog_instance.add_provider.assert_called_once()


def test_vastai_compute_can_disable_community_cloud():
    with (
        patch("dstack._internal.core.backends.vastai.compute.VastAIProvider") as vast_provider_cls,
        patch("dstack._internal.core.backends.vastai.compute.gpuhunt.Catalog") as catalog_cls,
        patch("dstack._internal.core.backends.vastai.compute.get_catalog_offers", return_value=[]),
    ):
        catalog_instance = catalog_cls.return_value
        compute = VastAICompute(_config(community_cloud=False))
        list(compute.get_offers(_requirements(), False))
        vast_provider_cls.assert_called_once()
        assert vast_provider_cls.call_args.kwargs["community_cloud"] is False
        catalog_instance.add_provider.assert_called_once()


def test_vastai_run_job_bids_on_spot_offer():
    compute = VastAICompute(_config())
    compute.api_client = MagicMock()
    compute.api_client.create_instance.return_value = 123

    _run_job(compute, _offer(spot=True, price=0.14, min_bid=0.1244444))

    assert compute.api_client.create_instance.call_args.kwargs["bid"] == 0.1244444


def test_vastai_run_job_does_not_bid_on_ondemand_offer():
    compute = VastAICompute(_config())
    compute.api_client = MagicMock()
    compute.api_client.create_instance.return_value = 123

    _run_job(compute, _offer(spot=False, price=0.24))

    assert compute.api_client.create_instance.call_args.kwargs["bid"] is None
