from unittest.mock import MagicMock

from dstack._internal.core.backends.cloudrift.compute import CloudRiftCompute
from dstack._internal.core.backends.cloudrift.models import CloudRiftConfig, CloudRiftCreds
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.runs import JobProvisioningData


def _compute() -> CloudRiftCompute:
    compute = CloudRiftCompute(CloudRiftConfig(creds=CloudRiftCreds(api_key="test")))
    compute.client = MagicMock()
    return compute


def _provisioning_data(ssh_port: int | None = None) -> JobProvisioningData:
    return JobProvisioningData(
        backend=BackendType.CLOUDRIFT,
        instance_type=InstanceType(
            name="rtx49-10c-kn.1",
            resources=Resources(
                cpus=7,
                memory_mib=48 * 1024,
                gpus=[Gpu(name="RTX4090", memory_mib=24 * 1024)],
                spot=False,
            ),
        ),
        instance_id="instance-id",
        hostname=None,
        internal_ip=None,
        region="ap-east-tw-kn-1",
        price=0.39,
        username="riftuser",
        ssh_port=ssh_port,
        dockerized=True,
    )


def _vm_instance_info(**overrides) -> dict:
    instance_info = {
        "node_mode": "VirtualMachine",
        "host_address": "211.21.50.85",
        "virtual_machines": [{"ready": True}],
        "port_mappings": [[22, 57001], [80, 57002]],
    }
    instance_info.update(overrides)
    return instance_info


def _offer() -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.CLOUDRIFT,
        instance=InstanceType(
            name="rtx49-10c-kn.1",
            resources=Resources(
                cpus=7,
                memory_mib=48 * 1024,
                gpus=[Gpu(name="RTX4090", memory_mib=24 * 1024)],
                spot=False,
            ),
        ),
        region="ap-east-tw-kn-1",
        price=0.39,
        availability=InstanceAvailability.AVAILABLE,
    )


class TestCloudRiftComputeCreateInstance:
    def test_waits_for_ssh_endpoint_from_cloudrift(self):
        compute = _compute()
        compute.client.deploy_instance.return_value = ["instance-id"]
        instance_config = InstanceConfiguration(
            project_name="main",
            instance_name="test-instance",
            user="test-user",
            ssh_keys=[SSHKey(public="ssh-rsa test")],
        )

        provisioning_data = compute.create_instance(
            instance_offer=_offer(),
            instance_config=instance_config,
            placement_group=None,
        )

        assert provisioning_data.instance_id == "instance-id"
        assert provisioning_data.hostname is None
        assert provisioning_data.ssh_port is None


class TestCloudRiftComputeUpdateProvisioningData:
    def test_sets_hostname_and_mapped_ssh_port(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        compute.client.get_instance_by_id.return_value = _vm_instance_info()

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname == "211.21.50.85"
        assert provisioning_data.ssh_port == 57001

    def test_accepts_string_port_mapping_values(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        compute.client.get_instance_by_id.return_value = _vm_instance_info(
            port_mappings=[["22", "57001"]]
        )

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname == "211.21.50.85"
        assert provisioning_data.ssh_port == 57001

    def test_uses_ssh_port_from_instructions_when_port_mappings_are_missing(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        compute.client.get_instance_by_id.return_value = _vm_instance_info(
            port_mappings=None,
            instructions={"placeholder_values": [["SSH_PORT", "-p 57001"]]},
        )

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname == "211.21.50.85"
        assert provisioning_data.ssh_port == 57001

    def test_uses_ssh_port_from_instructions_when_port_mappings_are_empty(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        compute.client.get_instance_by_id.return_value = _vm_instance_info(
            port_mappings=[],
            instructions={"placeholder_values": [["SSH_PORT", "-p 57001"]]},
        )

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname == "211.21.50.85"
        assert provisioning_data.ssh_port == 57001

    def test_uses_default_ssh_port_from_empty_ssh_port_instruction(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        compute.client.get_instance_by_id.return_value = _vm_instance_info(
            port_mappings=None,
            instructions={"placeholder_values": [["SSH_PORT", ""]]},
        )

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname == "211.21.50.85"
        assert provisioning_data.ssh_port == 22

    def test_uses_default_ssh_port_when_cloudrift_does_not_return_port_mapping_data(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        instance_info = _vm_instance_info()
        instance_info.pop("port_mappings")
        compute.client.get_instance_by_id.return_value = instance_info

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname == "211.21.50.85"
        assert provisioning_data.ssh_port == 22

    def test_uses_default_ssh_port_when_instructions_do_not_include_ssh_port(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        instance_info = _vm_instance_info(
            instructions={"placeholder_values": [["USERNAME", "riftuser"]]}
        )
        instance_info.pop("port_mappings")
        compute.client.get_instance_by_id.return_value = instance_info

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname == "211.21.50.85"
        assert provisioning_data.ssh_port == 22

    def test_waits_for_ssh_port_when_port_mappings_are_temporarily_missing(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        compute.client.get_instance_by_id.return_value = _vm_instance_info(port_mappings=[])

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname is None
        assert provisioning_data.ssh_port is None

    def test_waits_for_ssh_port_when_port_mappings_are_invalid(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        compute.client.get_instance_by_id.return_value = _vm_instance_info(
            port_mappings=[
                [22],
                [22, "not-a-port"],
                [22, 0],
                [22, 65536],
                [80, 57002],
            ]
        )

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname is None
        assert provisioning_data.ssh_port is None

    def test_waits_for_ssh_port_when_ssh_port_instruction_is_invalid(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        instance_info = _vm_instance_info(
            instructions={"placeholder_values": [["SSH_PORT", "-p not-a-port"]]}
        )
        instance_info.pop("port_mappings")
        compute.client.get_instance_by_id.return_value = instance_info

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname is None
        assert provisioning_data.ssh_port is None

    def test_does_not_update_before_vm_is_ready(self):
        compute = _compute()
        provisioning_data = _provisioning_data()
        compute.client.get_instance_by_id.return_value = _vm_instance_info(
            virtual_machines=[{"ready": False}]
        )

        compute.update_provisioning_data(
            provisioning_data=provisioning_data,
            project_ssh_public_key="ssh-rsa test",
            project_ssh_private_key="private",
        )

        assert provisioning_data.hostname is None
        assert provisioning_data.ssh_port is None
