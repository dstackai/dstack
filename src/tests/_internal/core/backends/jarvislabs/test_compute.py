from unittest.mock import MagicMock, patch

import pytest

from dstack._internal.core.backends.jarvislabs.compute import (
    JarvisLabsCompute,
    _get_disk_size_gb,
    _get_jarvislabs_gpu_type,
    _get_ssh_username,
    _raise_if_create_failed,
)
from dstack._internal.core.backends.jarvislabs.models import JarvisLabsConfig, JarvisLabsCreds
from dstack._internal.core.errors import NoCapacityError, ProvisioningError
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


def _compute() -> JarvisLabsCompute:
    compute = JarvisLabsCompute(
        JarvisLabsConfig(creds=JarvisLabsCreds(api_key="test"), regions=["india-noida-01"])
    )
    compute.api_client = MagicMock()
    compute.api_client.get_instance_status.return_value = {"status": "Running"}
    return compute


def _instance_config() -> InstanceConfiguration:
    return InstanceConfiguration(
        project_name="test-project",
        instance_name="jarvislabs-test",
        user="test-user",
        ssh_keys=[SSHKey(public="ssh-rsa AAAA test")],
    )


def _gpu_offer(
    *,
    gpu_name: str = "A100",
    gpu_memory_mib: int = 80 * 1024,
    disk_size_mib: int = 250 * 1024,
    spot: bool = False,
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


def test_get_jarvislabs_gpu_type_reconstructs_a100_80gb():
    assert _get_jarvislabs_gpu_type(_gpu_offer()) == "A100-80GB"
    assert _get_jarvislabs_gpu_type(_gpu_offer(gpu_memory_mib=40 * 1024)) == "A100"
    assert _get_jarvislabs_gpu_type(_gpu_offer(gpu_name="H100")) == "H100"


def test_get_disk_size_gb_clamps_to_jarvislabs_vm_minimum():
    assert _get_disk_size_gb(_cpu_offer(disk_size_mib=10 * 1024)) == 100
    assert _get_disk_size_gb(_gpu_offer(disk_size_mib=250 * 1024)) == 250


def test_create_gpu_instance_registers_ssh_key_and_creates_gpu_vm():
    compute = _compute()
    compute.api_client.create_gpu_vm.return_value = "123"

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.generate_unique_instance_name",
        return_value="dstack-test",
    ):
        provisioning_data = compute.create_instance(_gpu_offer(), _instance_config(), None)

    compute.api_client.add_ssh_key_if_needed.assert_called_once_with("ssh-rsa AAAA test")
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
    assert provisioning_data.backend_data is None


def test_create_gpu_instance_passes_spot_flag():
    compute = _compute()
    compute.api_client.create_gpu_vm.return_value = "123"

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.generate_unique_instance_name",
        return_value="dstack-test",
    ):
        compute.create_instance(_gpu_offer(spot=True), _instance_config(), None)

    compute.api_client.create_gpu_vm.assert_called_once_with(
        gpu_type="A100-80GB",
        num_gpus=1,
        is_spot=True,
        storage=250,
        region="india-noida-01",
        name="dstack-test",
    )


def test_create_cpu_instance_registers_ssh_key_and_creates_cpu_vm():
    compute = _compute()
    compute.api_client.create_cpu_vm.return_value = "456"

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.generate_unique_instance_name",
        return_value="dstack-cpu",
    ):
        provisioning_data = compute.create_instance(_cpu_offer(), _instance_config(), None)

    compute.api_client.add_ssh_key_if_needed.assert_called_once_with("ssh-rsa AAAA test")
    compute.api_client.create_cpu_vm.assert_called_once_with(
        vcpus=4,
        ram_gb=16,
        storage=100,
        region="india-noida-01",
        name="dstack-cpu",
    )
    assert provisioning_data.instance_id == "456"
    assert provisioning_data.backend_data is None


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


def test_terminate_instance_delegates_to_api_client():
    compute = _compute()

    compute.terminate_instance("123", "india-noida-01")

    compute.api_client.destroy_instance.assert_called_once_with(
        machine_id="123",
        region="india-noida-01",
    )


def test_create_instance_cleans_up_post_create_failure():
    compute = _compute()
    compute.api_client.create_gpu_vm.return_value = "123"
    compute.api_client.get_instance_status.return_value = {
        "status": "Failed",
        "error": "L4 not available at this moment, please try again later",
        "code": 404,
    }

    with patch(
        "dstack._internal.core.backends.jarvislabs.compute.generate_unique_instance_name",
        return_value="dstack-test",
    ):
        with pytest.raises(NoCapacityError):
            compute.create_instance(_gpu_offer(spot=True), _instance_config(), None)

    compute.api_client.destroy_instance.assert_called_once_with(
        machine_id="123",
        region="india-noida-01",
    )


def test_raise_if_create_failed_due_to_no_capacity():
    api_client = MagicMock()
    api_client.get_instance_status.return_value = {
        "status": "Failed",
        "error": "L4 not available at this moment, please try again later",
        "code": 404,
    }

    with patch("dstack._internal.core.backends.jarvislabs.compute.time.sleep"):
        with pytest.raises(NoCapacityError):
            _raise_if_create_failed(
                api_client=api_client,
                machine_id="123",
                region="india-noida-01",
            )


def test_raise_if_create_failed_raises_provisioning_error():
    api_client = MagicMock()
    api_client.get_instance_status.return_value = {
        "status": "Failed",
        "error": "image setup failed",
        "code": 500,
    }

    with patch("dstack._internal.core.backends.jarvislabs.compute.time.sleep"):
        with pytest.raises(ProvisioningError):
            _raise_if_create_failed(
                api_client=api_client,
                machine_id="123",
                region="india-noida-01",
            )
