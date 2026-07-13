from unittest.mock import MagicMock, patch

from dstack._internal.core.backends.oci.compute import OCICompute
from dstack._internal.core.backends.oci.models import OCIClientCreds, OCIConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
    SSHKey,
)


def _make_config(network_security_group_ids=None) -> OCIConfig:
    return OCIConfig(
        creds=OCIClientCreds(
            user="user",
            tenancy="tenancy",
            key_content="key",
            key_file=None,
            pass_phrase=None,
            fingerprint="fingerprint",
            region="us-ashburn-1",
        ),
        regions=["us-ashburn-1"],
        compartment_id="ocid1.compartment.oc1..compartment",
        subnet_ids_per_region={"us-ashburn-1": "ocid1.subnet.oc1..subnet"},
        network_security_group_ids=network_security_group_ids,
    )


def _make_offer() -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.OCI,
        instance=InstanceType(
            name="VM.Standard2.1",
            resources=Resources(cpus=1, memory_mib=15000, gpus=[], spot=False),
        ),
        region="us-ashburn-1",
        price=0.1,
        availability=InstanceAvailability.AVAILABLE,
        availability_zones=["AD-1"],
    )


def _make_instance_config(security_group=None) -> InstanceConfiguration:
    return InstanceConfiguration(
        project_name="test-project",
        instance_name="test-instance",
        user="test-user",
        ssh_keys=[SSHKey(public="ssh-rsa AAAA")],
        security_group=security_group,
    )


def _make_compute(config: OCIConfig) -> OCICompute:
    with patch("dstack._internal.core.backends.oci.compute.make_region_clients_map") as m:
        region = MagicMock()
        subnet = MagicMock()
        subnet.id = "ocid1.subnet.oc1..subnet"
        subnet.vcn_id = "ocid1.vcn.oc1..vcn"
        region.virtual_network_client.get_subnet.return_value.data = subnet
        m.return_value = {"us-ashburn-1": region}
        compute = OCICompute(config)
    return compute


class TestOCIComputeSecurityGroup:
    def _run_create_instance(self, compute, instance_config):
        with patch("dstack._internal.core.backends.oci.compute.resources") as res:
            res.VCN_CIDR = "10.0.0.0/16"
            res.RESTRICTED_VCN_CIDR = "10.1.0.0/16"
            res.get_marketplace_listing_and_package.return_value = (MagicMock(), MagicMock())
            res.get_or_create_security_group.return_value.id = "ocid1.nsg.oc1..managed"
            res.set_up_restricted_network_resources_in_region.return_value.id = (
                "ocid1.subnet.oc1..restricted"
            )
            res.launch_instance.return_value.id = "ocid1.instance.oc1..instance"
            compute.create_instance(_make_offer(), instance_config, placement_group=None)
        return res

    def test_default_creates_and_syncs_managed_security_group(self):
        compute = _make_compute(_make_config())
        res = self._run_create_instance(compute, _make_instance_config())

        res.get_or_create_security_group.assert_called_once()
        res.update_security_group_rules_for_runner_instances.assert_called_once()
        assert (
            res.launch_instance.call_args.kwargs["security_group_id"]
            == "ocid1.nsg.oc1..managed"
        )
        # The default/auto-managed-NSG path uses the original default subnet
        # and never touches the restricted VCN/subnet.
        res.set_up_restricted_network_resources_in_region.assert_not_called()
        assert (
            res.launch_instance.call_args.kwargs["subnet_id"] == "ocid1.subnet.oc1..subnet"
        )

    def test_per_region_custom_nsg_is_left_untouched(self):
        compute = _make_compute(
            _make_config(
                network_security_group_ids={"us-ashburn-1": "ocid1.nsg.oc1..custom"}
            )
        )
        res = self._run_create_instance(compute, _make_instance_config())

        res.get_or_create_security_group.assert_not_called()
        res.update_security_group_rules_for_runner_instances.assert_not_called()
        res.update_security_group_rules.assert_not_called()
        assert (
            res.launch_instance.call_args.kwargs["security_group_id"]
            == "ocid1.nsg.oc1..custom"
        )
        # A custom NSG routes the instance into a dedicated restricted VCN/subnet
        # (no security list), never the default one.
        res.set_up_restricted_network_resources_in_region.assert_called_once()
        assert (
            res.set_up_restricted_network_resources_in_region.call_args.kwargs["project_name"]
            == "test-project"
        )
        assert (
            res.launch_instance.call_args.kwargs["subnet_id"]
            == "ocid1.subnet.oc1..restricted"
        )

    def test_region_not_in_mapping_falls_back_to_managed(self):
        compute = _make_compute(
            _make_config(
                network_security_group_ids={"us-phoenix-1": "ocid1.nsg.oc1..other"}
            )
        )
        res = self._run_create_instance(compute, _make_instance_config())

        res.get_or_create_security_group.assert_called_once()
        res.update_security_group_rules_for_runner_instances.assert_called_once()
        assert (
            res.launch_instance.call_args.kwargs["security_group_id"]
            == "ocid1.nsg.oc1..managed"
        )
        res.set_up_restricted_network_resources_in_region.assert_not_called()
        assert (
            res.launch_instance.call_args.kwargs["subnet_id"] == "ocid1.subnet.oc1..subnet"
        )

    def test_instance_level_custom_nsg_is_left_untouched(self):
        compute = _make_compute(_make_config())
        res = self._run_create_instance(
            compute, _make_instance_config(security_group="ocid1.nsg.oc1..run")
        )

        res.get_or_create_security_group.assert_not_called()
        res.update_security_group_rules_for_runner_instances.assert_not_called()
        res.update_security_group_rules.assert_not_called()
        assert (
            res.launch_instance.call_args.kwargs["security_group_id"] == "ocid1.nsg.oc1..run"
        )
        res.set_up_restricted_network_resources_in_region.assert_called_once()
        assert (
            res.launch_instance.call_args.kwargs["subnet_id"]
            == "ocid1.subnet.oc1..restricted"
        )

    def test_instance_level_overrides_per_region_mapping(self):
        compute = _make_compute(
            _make_config(
                network_security_group_ids={"us-ashburn-1": "ocid1.nsg.oc1..project"}
            )
        )
        res = self._run_create_instance(
            compute, _make_instance_config(security_group="ocid1.nsg.oc1..run")
        )

        res.get_or_create_security_group.assert_not_called()
        res.update_security_group_rules_for_runner_instances.assert_not_called()
        assert (
            res.launch_instance.call_args.kwargs["security_group_id"] == "ocid1.nsg.oc1..run"
        )
        res.set_up_restricted_network_resources_in_region.assert_called_once()
        assert (
            res.launch_instance.call_args.kwargs["subnet_id"]
            == "ocid1.subnet.oc1..restricted"
        )


class TestGetOrCreateRestrictedSubnet:
    def test_creates_subnet_with_empty_security_list_ids(self):
        from dstack._internal.core.backends.oci import resources

        client = MagicMock()
        client.list_subnets.return_value.data = []
        client.list_subnets.return_value.next_page = None
        client.list_subnets.return_value.has_next_page = False

        resources.get_or_create_restricted_subnet(
            "dstack-test-project-restricted-subnet",
            "ocid1.vcn.oc1..vcn",
            "ocid1.compartment.oc1..compartment",
            client,
        )

        client.create_subnet.assert_called_once()
        details = client.create_subnet.call_args.args[0]
        assert details.security_list_ids == []
        assert details.vcn_id == "ocid1.vcn.oc1..vcn"
        assert details.display_name == "dstack-test-project-restricted-subnet"

    def test_returns_existing_subnet_without_creating(self):
        from dstack._internal.core.backends.oci import resources

        existing = MagicMock()
        client = MagicMock()
        client.list_subnets.return_value.data = [existing]
        client.list_subnets.return_value.next_page = None
        client.list_subnets.return_value.has_next_page = False

        result = resources.get_or_create_restricted_subnet(
            "dstack-test-project-restricted-subnet",
            "ocid1.vcn.oc1..vcn",
            "ocid1.compartment.oc1..compartment",
            client,
        )

        assert result is existing
        client.create_subnet.assert_not_called()
