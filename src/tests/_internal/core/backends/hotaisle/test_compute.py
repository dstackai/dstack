import subprocess
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from gpuhunt.providers.hotaisle import API_URL

from dstack._internal.core.backends.hotaisle.compute import (
    SSH_CONNECT_TIMEOUT_SECONDS,
    SSH_LAUNCH_TIMEOUT_SECONDS,
    HotAisleCompute,
    HotAisleInstanceBackendData,
    _run_ssh_command,
)
from dstack._internal.core.backends.hotaisle.models import HotAisleAPIKeyCreds, HotAisleConfig
from dstack._internal.core.errors import ProvisioningError
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

VM_SPECS = {
    "cpu_cores": 13,
    "ram_capacity": 224 * 1024**3,
    "disk_capacity": 12288 * 1024**3,
    "cpus": {"count": 1, "manufacturer": "Intel", "model": "Xeon Platinum 8470"},
    "gpus": [{"count": 1, "manufacturer": "AMD", "model": "MI300X"}],
}

BARE_METAL_SPECS = {
    "cpu_cores": 104,
    "ram_capacity": 2048 * 1024**3,
    "disk_capacity": 123839994396672,
    "cpus": [{"count": 2, "manufacturer": "Intel", "model": "Xeon Platinum 8470", "cores": 52}],
    "gpus": [{"count": 8, "manufacturer": "AMD", "model": "MI300X"}],
}


def _compute() -> HotAisleCompute:
    return HotAisleCompute(
        HotAisleConfig(team_handle="test-team", creds=HotAisleAPIKeyCreds(api_key="test-key"))
    )


def _compute_with_mocked_api_client() -> HotAisleCompute:
    compute = _compute()
    compute.api_client = MagicMock()
    return compute


def _instance_type(name: str) -> InstanceType:
    return InstanceType(
        name=name,
        resources=Resources(
            cpus=13,
            memory_mib=224 * 1024,
            gpus=[Gpu(name="MI300X", memory_mib=192 * 1024)],
            spot=False,
            disk=Disk(size_mib=12288 * 1024),
        ),
    )


def _offer(name: str, backend_data: dict) -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.HOTAISLE,
        instance=_instance_type(name),
        region="us-michigan-1",
        price=1.99,
        backend_data=backend_data,
        availability=InstanceAvailability.AVAILABLE,
    )


def _instance_config() -> InstanceConfiguration:
    return InstanceConfiguration(
        project_name="test-project",
        instance_name="test-instance",
        user="test-user",
        ssh_keys=[SSHKey(public="ssh-rsa AAAA test")],
    )


def _provisioning_data(
    backend_data: Optional[HotAisleInstanceBackendData],
) -> JobProvisioningData:
    return JobProvisioningData(
        backend=BackendType.HOTAISLE,
        instance_type=_instance_type("vm-mi300x-1"),
        instance_id="instance-id",
        hostname=None,
        internal_ip=None,
        region="us-michigan-1",
        price=1.99,
        username="hotaisle",
        ssh_port=22,
        dockerized=True,
        ssh_proxy=None,
        backend_data=backend_data.model_dump_json() if backend_data is not None else None,
    )


class TestGetAllOffersWithAvailability:
    def test_returns_vm_and_bare_metal_offers(self, requests_mock):
        requests_mock.get(
            f"{API_URL}/teams/test-team/virtual_machines/available/",
            json=[{"OnDemandPrice": 199, "Specs": VM_SPECS}],
        )
        requests_mock.get(
            f"{API_URL}/teams/test-team/bare_metal/available/",
            json=[{"OnDemandPrice": 2712, "Specs": BARE_METAL_SPECS}],
        )

        offers = _compute().get_all_offers_with_availability(unallocated_resources=False)

        assert [(offer.instance.name, offer.backend_data) for offer in offers] == [
            ("vm-mi300x-1", {"vm_specs": VM_SPECS}),
            ("bm-mi300x-8", {"bare_metal_specs": BARE_METAL_SPECS}),
        ]


class TestCreateInstance:
    def test_creates_vm(self):
        compute = _compute_with_mocked_api_client()
        compute.api_client.create_virtual_machine.return_value = {
            "name": "vm-name",
            "ip_address": "10.0.0.1",
        }

        provisioning_data = compute.create_instance(
            _offer("vm-mi300x-1", {"vm_specs": VM_SPECS}), _instance_config(), None
        )

        compute.api_client.upload_ssh_key.assert_called_once_with("ssh-rsa AAAA test")
        compute.api_client.create_virtual_machine.assert_called_once_with(VM_SPECS)
        compute.api_client.reserve_bare_metal_server.assert_not_called()
        assert provisioning_data.instance_id == "vm-name"
        assert HotAisleInstanceBackendData.load(
            provisioning_data.backend_data
        ) == HotAisleInstanceBackendData(ip_address="10.0.0.1", bare_metal=False)

    def test_reserves_bare_metal_server(self):
        compute = _compute_with_mocked_api_client()
        compute.api_client.reserve_bare_metal_server.return_value = {
            "deployment_id": "deployment-id",
            "name": "server-01",
            "ip_address": "10.0.0.2",
        }

        provisioning_data = compute.create_instance(
            _offer("bm-mi300x-8", {"bare_metal_specs": BARE_METAL_SPECS}),
            _instance_config(),
            None,
        )

        compute.api_client.upload_ssh_key.assert_called_once_with("ssh-rsa AAAA test")
        compute.api_client.reserve_bare_metal_server.assert_called_once_with(
            specs=BARE_METAL_SPECS, description="test-instance"
        )
        compute.api_client.create_virtual_machine.assert_not_called()
        assert provisioning_data.instance_id == "deployment-id"
        assert provisioning_data.username == "hotaisle"
        assert HotAisleInstanceBackendData.load(
            provisioning_data.backend_data
        ) == HotAisleInstanceBackendData(ip_address="10.0.0.2", bare_metal=True)


@patch("dstack._internal.core.backends.hotaisle.compute._run_ssh_command", return_value=True)
class TestUpdateProvisioningData:
    def test_starts_shim_on_running_vm(self, ssh_mock):
        compute = _compute_with_mocked_api_client()
        compute.api_client.get_vm_state.return_value = "running"
        provisioning_data = _provisioning_data(HotAisleInstanceBackendData(ip_address="10.0.0.1"))

        compute.update_provisioning_data(provisioning_data, "public-key", "private-key")

        compute.api_client.get_vm_state.assert_called_once_with("instance-id")
        assert provisioning_data.hostname == "10.0.0.1"
        ssh_mock.assert_called_once()
        assert ssh_mock.call_args.kwargs["hostname"] == "10.0.0.1"

    def test_retries_if_shim_fails_to_start(self, ssh_mock):
        ssh_mock.return_value = False
        compute = _compute_with_mocked_api_client()
        compute.api_client.get_vm_state.return_value = "running"
        provisioning_data = _provisioning_data(HotAisleInstanceBackendData(ip_address="10.0.0.1"))

        compute.update_provisioning_data(provisioning_data, "public-key", "private-key")

        ssh_mock.assert_called_once()
        assert provisioning_data.hostname is None

    def test_waits_for_vm_to_run(self, ssh_mock):
        compute = _compute_with_mocked_api_client()
        compute.api_client.get_vm_state.return_value = "shut off"
        provisioning_data = _provisioning_data(HotAisleInstanceBackendData(ip_address="10.0.0.1"))

        compute.update_provisioning_data(provisioning_data, "public-key", "private-key")

        assert provisioning_data.hostname is None
        ssh_mock.assert_not_called()

    def test_starts_shim_on_installed_bare_metal_server(self, ssh_mock):
        compute = _compute_with_mocked_api_client()
        compute.api_client.get_bare_metal_server.return_value = {
            "os_status": {"os_install_status": "installed"}
        }
        provisioning_data = _provisioning_data(
            HotAisleInstanceBackendData(ip_address="10.0.0.2", bare_metal=True)
        )

        compute.update_provisioning_data(provisioning_data, "public-key", "private-key")

        compute.api_client.get_bare_metal_server.assert_called_once_with("instance-id")
        compute.api_client.get_vm_state.assert_not_called()
        assert provisioning_data.hostname == "10.0.0.2"
        ssh_mock.assert_called_once()
        assert ssh_mock.call_args.kwargs["hostname"] == "10.0.0.2"

    @pytest.mark.parametrize(
        "server_data",
        [
            {"os_status": {"os_install_status": "installing_os"}},
            {"os_status": {"os_install_status": "first_boot_tasks"}},
            {"os_status": None},
            {},
        ],
    )
    def test_waits_for_bare_metal_os_installation(self, ssh_mock, server_data):
        compute = _compute_with_mocked_api_client()
        compute.api_client.get_bare_metal_server.return_value = server_data
        provisioning_data = _provisioning_data(
            HotAisleInstanceBackendData(ip_address="10.0.0.2", bare_metal=True)
        )

        compute.update_provisioning_data(provisioning_data, "public-key", "private-key")

        assert provisioning_data.hostname is None
        ssh_mock.assert_not_called()

    def test_raises_on_failed_bare_metal_os_installation(self, ssh_mock):
        compute = _compute_with_mocked_api_client()
        compute.api_client.get_bare_metal_server.return_value = {
            "os_status": {"os_install_status": "failed"}
        }
        provisioning_data = _provisioning_data(
            HotAisleInstanceBackendData(ip_address="10.0.0.2", bare_metal=True)
        )

        with pytest.raises(ProvisioningError):
            compute.update_provisioning_data(provisioning_data, "public-key", "private-key")
        ssh_mock.assert_not_called()


class TestTerminateInstance:
    def test_terminates_vm(self):
        compute = _compute_with_mocked_api_client()

        compute.terminate_instance(
            "vm-name",
            "us-michigan-1",
            HotAisleInstanceBackendData(ip_address="10.0.0.1").model_dump_json(),
        )

        compute.api_client.terminate_virtual_machine.assert_called_once_with("vm-name")
        compute.api_client.release_bare_metal_server.assert_not_called()

    def test_terminates_vm_without_backend_data(self):
        compute = _compute_with_mocked_api_client()

        compute.terminate_instance("vm-name", "us-michigan-1", None)

        compute.api_client.terminate_virtual_machine.assert_called_once_with("vm-name")

    def test_releases_bare_metal_server(self):
        compute = _compute_with_mocked_api_client()

        compute.terminate_instance(
            "deployment-id",
            "us-michigan-1",
            HotAisleInstanceBackendData(ip_address="10.0.0.2", bare_metal=True).model_dump_json(),
        )

        compute.api_client.release_bare_metal_server.assert_called_once_with("deployment-id")
        compute.api_client.terminate_virtual_machine.assert_not_called()


@patch("dstack._internal.core.backends.hotaisle.compute.subprocess.run")
class TestRunSSHCommand:
    def test_returns_true_on_success(self, run_mock):
        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0, stderr="")

        assert _run_ssh_command("10.0.0.1", "private-key", "true")

        args = run_mock.call_args.args[0]
        assert "hotaisle@10.0.0.1" in args
        assert f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}" in args
        assert run_mock.call_args.kwargs["timeout"] == SSH_LAUNCH_TIMEOUT_SECONDS

    @pytest.mark.parametrize(
        "run_result",
        [
            subprocess.CompletedProcess(args=[], returncode=255, stderr="Connection refused"),
            subprocess.TimeoutExpired(cmd="ssh", timeout=SSH_LAUNCH_TIMEOUT_SECONDS),
        ],
        ids=["ssh-fails", "ssh-times-out"],
    )
    def test_returns_false_on_failure(self, run_mock, run_result):
        if isinstance(run_result, Exception):
            run_mock.side_effect = run_result
        else:
            run_mock.return_value = run_result

        assert not _run_ssh_command("10.0.0.1", "private-key", "true")
