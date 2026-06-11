from unittest.mock import MagicMock, call, patch

import pytest

from dstack._internal.core.backends.jarvislabs.compute import (
    CONFIGURABLE_DISK_SIZE,
    JarvisLabsCompute,
    JarvisLabsInstanceBackendData,
    _get_disk_size_gb,
    _get_jarvislabs_gpu_type,
    _get_ssh_username,
)
from dstack._internal.core.backends.jarvislabs.models import JarvisLabsConfig, JarvisLabsCreds
from dstack._internal.core.errors import BackendError, NoCapacityError, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobProvisioningData, Requirements


def _compute() -> JarvisLabsCompute:
    compute = JarvisLabsCompute(
        JarvisLabsConfig(creds=JarvisLabsCreds(api_key="test"), regions=["india-noida-01"])
    )
    compute.api_client = MagicMock()
    compute.api_client.create_ssh_key.return_value = "ssh-key-id"
    compute.api_client.get_instance_status.return_value = {"status": "Running"}
    return compute


def _instance_config(ssh_keys: list[SSHKey] | None = None) -> InstanceConfiguration:
    return InstanceConfiguration(
        project_name="test-project",
        instance_name="jarvislabs-test",
        user="test-user",
        ssh_keys=ssh_keys or [SSHKey(public="ssh-rsa AAAA test")],
    )


def _gpu_offer(
    *,
    gpu_name: str = "A100",
    gpu_memory_mib: int = 80 * 1024,
    disk_size_mib: int = 250 * 1024,
    spot: bool = False,
    backend_data: dict | None = None,
) -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.JARVISLABS,
        instance=InstanceType(
            name=f"{gpu_name}-1x",
            resources=Resources(
                cpus=28,
                memory_mib=112 * 1024,
                gpus=[Gpu(name=gpu_name, memory_mib=gpu_memory_mib)],
                spot=spot,
                disk=Disk(size_mib=disk_size_mib),
            ),
        ),
        region="india-noida-01",
        price=1.49,
        backend_data=backend_data or {},
        availability=InstanceAvailability.AVAILABLE,
    )


def _cpu_offer(*, disk_size_mib: int = 10 * 1024) -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.JARVISLABS,
        instance=InstanceType(
            name="cpu-4x16",
            resources=Resources(
                cpus=4,
                memory_mib=16 * 1024,
                gpus=[],
                spot=False,
                disk=Disk(size_mib=disk_size_mib),
            ),
        ),
        region="india-noida-01",
        price=0.0992,
        availability=InstanceAvailability.AVAILABLE,
    )


def _cpu_catalog_offer(*, disk_size_mib: int = 10 * 1024) -> InstanceOffer:
    offer = _cpu_offer(disk_size_mib=disk_size_mib)
    return InstanceOffer(
        backend=offer.backend,
        instance=offer.instance,
        region=offer.region,
        price=offer.price,
    )


def test_get_jarvislabs_gpu_type_uses_backend_data_or_gpu_name():
    assert (
        _get_jarvislabs_gpu_type(_gpu_offer(backend_data={"gpu_type": "A100-80GB"})) == "A100-80GB"
    )
    assert _get_jarvislabs_gpu_type(_gpu_offer()) == "A100"
    assert _get_jarvislabs_gpu_type(_gpu_offer(gpu_name="H100")) == "H100"
    assert (
        _get_jarvislabs_gpu_type(
            _gpu_offer(
                gpu_name="RTXPRO6000",
                gpu_memory_mib=96 * 1024,
                backend_data={"gpu_type": "RTX-PRO6000"},
            )
        )
        == "RTX-PRO6000"
    )


def test_get_jarvislabs_gpu_type_prefers_backend_data():
    offer = _gpu_offer(
        gpu_name="RTXPRO6000",
        gpu_memory_mib=96 * 1024,
        backend_data={"gpu_type": "RTX PRO 6000"},
    )

    assert _get_jarvislabs_gpu_type(offer) == "RTX PRO 6000"


def test_get_disk_size_gb_clamps_to_jarvislabs_vm_minimum():
    assert _get_disk_size_gb(_cpu_offer(disk_size_mib=10 * 1024)) == 100
    assert _get_disk_size_gb(_gpu_offer(disk_size_mib=250 * 1024)) == 250


def test_get_all_offers_uses_configurable_disk_size():
    compute = _compute()

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.get_catalog_offers",
        return_value=[_cpu_catalog_offer()],
    ) as m:
        offers = compute.get_all_offers_with_availability()

    assert len(offers) == 1
    assert offers[0].availability == InstanceAvailability.AVAILABLE
    m.assert_called_once_with(
        backend=BackendType.JARVISLABS,
        locations=["india-noida-01"],
        catalog=compute._catalog,
        configurable_disk_size=CONFIGURABLE_DISK_SIZE,
    )


def test_get_offers_reuses_all_offers_cache_and_modifies_disk_size():
    compute = _compute()
    compute.get_all_offers_with_availability = MagicMock(
        return_value=[_cpu_offer(disk_size_mib=100 * 1024)]
    )

    offers_250gb = list(compute.get_offers(Requirements(resources=ResourcesSpec(disk="250GB"))))
    offers_300gb = list(compute.get_offers(Requirements(resources=ResourcesSpec(disk="300GB"))))

    assert len(offers_250gb) == 1
    assert offers_250gb[0].instance.resources.disk.size_mib == 250 * 1024
    assert len(offers_300gb) == 1
    assert offers_300gb[0].instance.resources.disk.size_mib == 300 * 1024
    compute.get_all_offers_with_availability.assert_called_once()


def test_create_gpu_instance_creates_ssh_key_and_gpu_vm():
    compute = _compute()
    compute.api_client.create_gpu_vm.return_value = "123"

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.generate_unique_instance_name",
        return_value="dstack-test",
    ):
        provisioning_data = compute.create_instance(
            _gpu_offer(backend_data={"gpu_type": "A100-80GB"}), _instance_config(), None
        )

    compute.api_client.create_ssh_key.assert_called_once_with(
        public_key="ssh-rsa AAAA test",
        key_name="dstack-test-0.key",
    )
    compute.api_client.create_gpu_vm.assert_called_once_with(
        gpu_type="A100-80GB",
        num_gpus=1,
        is_spot=False,
        storage=250,
        region="india-noida-01",
        name="dstack-test",
    )
    assert provisioning_data.instance_id == "123"
    assert provisioning_data.username == "ubuntu"
    assert provisioning_data.dockerized is True
    backend_data = JarvisLabsInstanceBackendData.load(provisioning_data.backend_data)
    assert backend_data.ssh_key_ids == ["ssh-key-id"]
    compute.api_client.get_instance_status.assert_not_called()


def test_create_gpu_instance_passes_spot_flag():
    compute = _compute()
    compute.api_client.create_gpu_vm.return_value = "123"

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.generate_unique_instance_name",
        return_value="dstack-test",
    ):
        compute.create_instance(
            _gpu_offer(spot=True, backend_data={"gpu_type": "A100-80GB"}),
            _instance_config(),
            None,
        )

    compute.api_client.create_gpu_vm.assert_called_once_with(
        gpu_type="A100-80GB",
        num_gpus=1,
        is_spot=True,
        storage=250,
        region="india-noida-01",
        name="dstack-test",
    )


def test_create_rtx_pro_6000_instance_uses_jarvislabs_gpu_type_from_backend_data():
    compute = _compute()
    compute.api_client.create_gpu_vm.return_value = "123"
    offer = _gpu_offer(
        gpu_name="RTXPRO6000",
        gpu_memory_mib=96 * 1024,
        backend_data={"gpu_type": "RTX-PRO6000"},
    )

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.generate_unique_instance_name",
        return_value="dstack-test",
    ):
        compute.create_instance(offer, _instance_config(), None)

    compute.api_client.create_gpu_vm.assert_called_once_with(
        gpu_type="RTX-PRO6000",
        num_gpus=1,
        is_spot=False,
        storage=250,
        region="india-noida-01",
        name="dstack-test",
    )


def test_create_cpu_instance_creates_ssh_key_and_cpu_vm():
    compute = _compute()
    compute.api_client.create_cpu_vm.return_value = "456"

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.generate_unique_instance_name",
        return_value="dstack-cpu",
    ):
        provisioning_data = compute.create_instance(_cpu_offer(), _instance_config(), None)

    compute.api_client.create_ssh_key.assert_called_once_with(
        public_key="ssh-rsa AAAA test",
        key_name="dstack-cpu-0.key",
    )
    compute.api_client.create_cpu_vm.assert_called_once_with(
        vcpus=4,
        ram_gb=16,
        storage=100,
        region="india-noida-01",
        name="dstack-cpu",
    )
    assert provisioning_data.instance_id == "456"
    backend_data = JarvisLabsInstanceBackendData.load(provisioning_data.backend_data)
    assert backend_data.ssh_key_ids == ["ssh-key-id"]


def test_update_provisioning_data_sets_hostname_and_starts_runner():
    compute = _compute()
    compute.api_client.get_instance.return_value = {
        "machine_id": 123,
        "status": "Running",
        "public_ip": "203.0.113.10",
        "ssh_str": "ssh -o StrictHostKeyChecking=no ubuntu@203.0.113.10",
    }
    provisioning_data = JobProvisioningData(
        backend=BackendType.JARVISLABS,
        instance_type=_gpu_offer().instance,
        instance_id="123",
        region="india-noida-01",
        price=1.49,
        username="ubuntu",
        ssh_port=22,
        dockerized=True,
    )

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute._start_runner", return_value=True
    ) as m:
        compute.update_provisioning_data(
            provisioning_data,
            project_ssh_public_key="ssh-rsa AAAA test",
            project_ssh_private_key="private-key",
        )

    assert provisioning_data.hostname == "203.0.113.10"
    assert provisioning_data.username == "ubuntu"
    m.assert_called_once_with(
        hostname="203.0.113.10",
        username="ubuntu",
        project_ssh_private_key="private-key",
        arch=None,
    )


def test_update_provisioning_data_does_not_set_hostname_until_runner_starts():
    compute = _compute()
    compute.api_client.get_instance.return_value = {
        "machine_id": 123,
        "status": "Running",
        "public_ip": "203.0.113.10",
        "ssh_str": "ssh -o StrictHostKeyChecking=no ubuntu@203.0.113.10",
    }
    provisioning_data = JobProvisioningData(
        backend=BackendType.JARVISLABS,
        instance_type=_gpu_offer().instance,
        instance_id="123",
        region="india-noida-01",
        price=1.49,
        username="ubuntu",
        ssh_port=22,
        dockerized=True,
    )

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute._start_runner", return_value=False
    ):
        compute.update_provisioning_data(
            provisioning_data,
            project_ssh_public_key="ssh-rsa AAAA test",
            project_ssh_private_key="private-key",
        )

    assert provisioning_data.hostname is None


def test_get_ssh_username_parses_jarvislabs_ssh_command():
    assert (
        _get_ssh_username({"ssh_str": "ssh -o StrictHostKeyChecking=no ubuntu@203.0.113.10"})
        == "ubuntu"
    )
    assert _get_ssh_username({"ssh_str": "ssh -p 22 root@203.0.113.10"}) == "root"
    assert _get_ssh_username({}) == "ubuntu"


def test_terminate_instance_delegates_to_api_client_without_backend_data():
    compute = _compute()

    compute.terminate_instance("123", "india-noida-01")

    compute.api_client.destroy_instance.assert_called_once_with(
        machine_id="123",
        region="india-noida-01",
    )
    compute.api_client.delete_ssh_key.assert_not_called()


def test_terminate_instance_deletes_created_ssh_keys():
    compute = _compute()
    backend_data = JarvisLabsInstanceBackendData(
        ssh_key_ids=["ssh-key-id-1", "ssh-key-id-2"]
    ).json()

    compute.terminate_instance("123", "india-noida-01", backend_data)

    compute.api_client.destroy_instance.assert_called_once_with(
        machine_id="123",
        region="india-noida-01",
    )
    assert compute.api_client.delete_ssh_key.call_args_list == [
        call("ssh-key-id-1"),
        call("ssh-key-id-2"),
    ]


def test_create_instance_cleans_up_ssh_key_on_create_failure():
    compute = _compute()
    compute.api_client.create_gpu_vm.side_effect = NoCapacityError(
        "L4 not available at this moment, please try again later"
    )

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.generate_unique_instance_name",
        return_value="dstack-test",
    ):
        with pytest.raises(NoCapacityError):
            compute.create_instance(_gpu_offer(spot=True), _instance_config(), None)

    compute.api_client.destroy_instance.assert_not_called()
    compute.api_client.delete_ssh_key.assert_called_once_with("ssh-key-id")


def test_create_instance_cleans_up_created_ssh_key_if_later_ssh_key_create_fails():
    compute = _compute()
    compute.api_client.create_ssh_key.side_effect = [
        "ssh-key-id-1",
        BackendError("ssh create failed"),
    ]
    instance_config = _instance_config(
        ssh_keys=[
            SSHKey(public="ssh-rsa AAAA test-1"),
            SSHKey(public="ssh-rsa BBBB test-2"),
        ]
    )

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.generate_unique_instance_name",
        return_value="dstack-test",
    ):
        with pytest.raises(BackendError, match="ssh create failed"):
            compute.create_instance(_gpu_offer(), instance_config, None)

    compute.api_client.create_gpu_vm.assert_not_called()
    compute.api_client.delete_ssh_key.assert_called_once_with("ssh-key-id-1")


def test_update_provisioning_data_raises_provisioning_error_from_failed_capacity_status():
    compute = _compute()
    compute.api_client.get_instance.return_value = None
    compute.api_client.get_instance_status.return_value = {
        "status": "Failed",
        "error": "L4 not available at this moment, please try again later",
        "code": 404,
    }
    provisioning_data = JobProvisioningData(
        backend=BackendType.JARVISLABS,
        instance_type=_gpu_offer().instance,
        instance_id="123",
        region="india-noida-01",
        price=1.49,
        username="ubuntu",
        ssh_port=22,
        dockerized=True,
    )

    with pytest.raises(ProvisioningError):
        compute.update_provisioning_data(
            provisioning_data,
            project_ssh_public_key="ssh-rsa AAAA test",
            project_ssh_private_key="private-key",
        )


def test_update_provisioning_data_raises_provisioning_error_from_failed_status():
    compute = _compute()
    compute.api_client.get_instance.return_value = None
    compute.api_client.get_instance_status.return_value = {
        "status": "Failed",
        "error": "image setup failed",
        "code": 500,
    }
    provisioning_data = JobProvisioningData(
        backend=BackendType.JARVISLABS,
        instance_type=_gpu_offer().instance,
        instance_id="123",
        region="india-noida-01",
        price=1.49,
        username="ubuntu",
        ssh_port=22,
        dockerized=True,
    )

    with pytest.raises(ProvisioningError):
        compute.update_provisioning_data(
            provisioning_data,
            project_ssh_public_key="ssh-rsa AAAA test",
            project_ssh_private_key="private-key",
        )
