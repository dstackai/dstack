import shlex
from unittest.mock import MagicMock, patch

import pytest
from gpuhunt import RawCatalogItem

from dstack._internal.core.backends.base.compute import (
    ComputeWithInstanceVolumesSupport,
    ComputeWithMultinodeSupport,
    ComputeWithPrivilegedSupport,
)
from dstack._internal.core.backends.seeweb.api_client import SeewebPlanAvailability
from dstack._internal.core.backends.seeweb.compute import (
    SeewebCompute,
    SeewebInstanceBackendData,
    _select_image,
)
from dstack._internal.core.backends.seeweb.models import SeewebAPITokenCreds, SeewebConfig
from dstack._internal.core.errors import BackendError, NoCapacityError, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.runs import JobProvisioningData


def _config(regions=None) -> SeewebConfig:
    return SeewebConfig(regions=regions, creds=SeewebAPITokenCreds(api_token="tok"))


def _compute(regions=None) -> SeewebCompute:
    compute = SeewebCompute(_config(regions))
    compute.api_client = MagicMock()
    return compute


def _raw(name: str, gpu: str, location: str = "it-fr2") -> RawCatalogItem:
    return RawCatalogItem(
        instance_name=name,
        location=location,
        price=0.38,
        cpu=4,
        memory=32.0,
        gpu_count=1,
        gpu_name=gpu,
        gpu_memory=24.0,
        gpu_vendor="nvidia",
        spot=False,
        disk_size=100.0,
    )


def _gpu_offer(name: str = "ECS1GPU7") -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.SEEWEB,
        instance=InstanceType(
            name=name,
            resources=Resources(
                cpus=8,
                memory_mib=32 * 1024,
                gpus=[Gpu(name="L40S", memory_mib=48 * 1024)],
                spot=False,
                disk=Disk(size_mib=500 * 1024),
            ),
        ),
        region="it-fr2",
        price=0.85,
        availability=InstanceAvailability.AVAILABLE,
    )


def _instance_config(public_key: str = "ssh-ed25519 AAAATEST test") -> InstanceConfiguration:
    return InstanceConfiguration(
        project_name="project",
        instance_name="seeweb-test",
        user="user",
        ssh_keys=[SSHKey(public=public_key)],
    )


def _provisioning_data(action_id: int | None = 35) -> JobProvisioningData:
    return JobProvisioningData(
        backend=BackendType.SEEWEB,
        instance_type=_gpu_offer().instance,
        instance_id="ec-test",
        hostname=None,
        internal_ip=None,
        region="it-fr2",
        price=0.85,
        username="root",
        ssh_port=22,
        dockerized=True,
        ssh_proxy=None,
        backend_data=SeewebInstanceBackendData(action_id=action_id).json(),
    )


def test_vm_capability_mixins_are_enabled():
    assert issubclass(SeewebCompute, ComputeWithPrivilegedSupport)
    assert issubclass(SeewebCompute, ComputeWithInstanceVolumesSupport)
    assert issubclass(SeewebCompute, ComputeWithMultinodeSupport)


def test_get_offers_marks_only_creatable_as_available():
    raws = [_raw("ECS1GPU6", "L4"), _raw("ECS1GPU11", "A30")]
    with (
        patch(
            "dstack._internal.core.backends.seeweb.compute.SeewebProvider.get",
            return_value=raws,
        ),
        patch(
            "dstack._internal.core.backends.seeweb.api_client.SeewebApiClient"
            ".get_available_plan_regions",
            return_value={("ECS1GPU6", "it-fr2")},
        ),
    ):
        offers = SeewebCompute(_config()).get_offers_by_requirements(
            requirements=None, full_offers=False
        )

    by_name = {offer.instance.name: offer for offer in offers}
    assert by_name["ECS1GPU6"].availability == InstanceAvailability.AVAILABLE
    assert by_name["ECS1GPU11"].availability == InstanceAvailability.NOT_AVAILABLE
    assert by_name["ECS1GPU6"].instance.resources.gpus[0].name == "L4"


def test_get_offers_filters_configured_regions():
    raws = [
        _raw("ECS1GPU7", "L40S", "it-fr2"),
        _raw("ECS1GPU7", "L40S", "it-mi2"),
    ]
    with (
        patch(
            "dstack._internal.core.backends.seeweb.compute.SeewebProvider.get",
            return_value=raws,
        ),
        patch(
            "dstack._internal.core.backends.seeweb.api_client.SeewebApiClient"
            ".get_available_plan_regions",
            return_value={("ECS1GPU7", "it-fr2"), ("ECS1GPU7", "it-mi2")},
        ),
    ):
        offers = SeewebCompute(_config(["it-mi2"])).get_offers_by_requirements(
            requirements=None, full_offers=False
        )

    assert [offer.region for offer in offers] == ["it-mi2"]


def test_select_image_prefers_uefi_image():
    availability = SeewebPlanAvailability(
        regions=frozenset({"it-fr2"}),
        images=(
            "ubuntu-2204-nvidia-driver",
            "ubuntu-2204-uefi-nvidia-driver",
        ),
    )

    assert (
        _select_image(
            availability=availability,
            plan_name="ECS1GPU7",
            region="it-fr2",
            is_gpu=True,
        )
        == "ubuntu-2204-uefi-nvidia-driver"
    )


def test_select_image_rejects_unavailable_plan():
    with pytest.raises(NoCapacityError, match="not available"):
        _select_image(
            availability=None,
            plan_name="ECS1GPU7",
            region="it-fr2",
            is_gpu=True,
        )


def test_select_image_rejects_unsupported_images():
    availability = SeewebPlanAvailability(
        regions=frozenset({"it-fr2"}),
        images=("debian-12",),
    )

    with pytest.raises(BackendError, match="no supported GPU image"):
        _select_image(
            availability=availability,
            plan_name="ECS1GPU7",
            region="it-fr2",
            is_gpu=True,
        )


def test_create_instance_uses_allowed_image_and_quotes_ssh_key():
    compute = _compute()
    public_key = "ssh-ed25519 AAAATEST comment with ' quote"
    compute.api_client.get_available_plans.return_value = {
        "ECS1GPU7": SeewebPlanAvailability(
            regions=frozenset({"it-fr2"}),
            images=("ubuntu-2204-uefi-nvidia-driver",),
        )
    }
    compute.api_client.get_or_create_ssh_key.return_value = "dstack-key"
    compute.api_client.create_server.return_value = ({"name": "ec-test"}, 35)

    with (
        patch(
            "dstack._internal.core.backends.seeweb.compute.generate_unique_instance_name",
            return_value="dstack-seeweb-test",
        ),
        patch(
            "dstack._internal.core.backends.seeweb.compute.get_shim_commands",
            return_value=["prepare-shim", "start-shim"],
        ),
    ):
        provisioning_data = compute.create_instance(
            _gpu_offer(), _instance_config(public_key), placement_group=None
        )

    body = compute.api_client.create_server.call_args.args[0]
    assert body["plan"] == "ECS1GPU7"
    assert body["location"] == "it-fr2"
    assert body["image"] == "ubuntu-2204-uefi-nvidia-driver"
    assert body["ssh_key"] == "dstack-key"
    assert f"printf '%s\\n' {shlex.quote(public_key)}" in body["user_customize"]
    assert 'echo "ssh-' not in body["user_customize"]
    assert "prepare-shim" in body["user_customize"]
    assert "start-shim" not in body["user_customize"]
    assert "EnvironmentFile=/etc/dstack-shim.env" in body["user_customize"]
    assert body["user_customize"].endswith("systemctl enable dstack-shim.service")
    assert provisioning_data.instance_id == "ec-test"
    assert provisioning_data.hostname is None
    assert provisioning_data.username == "root"
    assert SeewebInstanceBackendData.load(provisioning_data.backend_data).action_id == 35


def test_update_provisioning_data_waits_for_action():
    compute = _compute()
    compute.api_client.get_action.return_value = {"status": "in-progress"}
    provisioning_data = _provisioning_data()

    compute.update_provisioning_data(provisioning_data, "public", "private")

    assert provisioning_data.hostname is None
    compute.api_client.get_server.assert_not_called()


def test_update_provisioning_data_sets_hostname_after_completed_action():
    compute = _compute()
    compute.api_client.get_action.return_value = {"status": "completed"}
    compute.api_client.get_server.return_value = {
        "name": "ec-test",
        "status": "Booted",
        "ipv4": "192.0.2.1",
    }
    provisioning_data = _provisioning_data()

    compute.update_provisioning_data(provisioning_data, "public", "private")

    assert provisioning_data.hostname == "192.0.2.1"


def test_update_provisioning_data_raises_for_failed_action():
    compute = _compute()
    compute.api_client.get_action.return_value = {"status": "failed"}

    with pytest.raises(ProvisioningError, match="entered status 'failed'"):
        compute.update_provisioning_data(_provisioning_data(), "public", "private")


def test_update_provisioning_data_raises_for_failed_server():
    compute = _compute()
    compute.api_client.get_server.return_value = {
        "name": "ec-test",
        "status": "Error",
    }

    with pytest.raises(ProvisioningError, match="entered status 'error'"):
        compute.update_provisioning_data(_provisioning_data(action_id=None), "public", "private")


def test_terminate_instance_delegates_to_idempotent_api():
    compute = _compute()

    compute.terminate_instance("ec-test", "it-fr2")

    compute.api_client.delete_server.assert_called_once_with("ec-test")
