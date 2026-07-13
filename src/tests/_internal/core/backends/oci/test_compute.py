from unittest.mock import MagicMock, patch

import oci

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
    """
    All instances - default (auto-managed NSG) or custom-NSG - share the same
    subnet/VCN, since OCI NSGs are VCN-scoped and only attach to VNICs in the
    same VCN they live in. `create_instance` must never route a custom-NSG
    instance to some other subnet.
    """

    def _run_create_instance(self, compute, instance_config):
        with patch("dstack._internal.core.backends.oci.compute.resources") as res:
            res.VCN_CIDR = "10.0.0.0/16"
            res.get_marketplace_listing_and_package.return_value = (MagicMock(), MagicMock())
            res.get_or_create_security_group.return_value.id = "ocid1.nsg.oc1..managed"
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
        # A custom NSG uses the same shared default subnet as auto-managed
        # instances - there is no separate subnet/VCN for custom-NSG instances.
        assert (
            res.launch_instance.call_args.kwargs["subnet_id"] == "ocid1.subnet.oc1..subnet"
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
        assert (
            res.launch_instance.call_args.kwargs["subnet_id"] == "ocid1.subnet.oc1..subnet"
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
        assert (
            res.launch_instance.call_args.kwargs["subnet_id"] == "ocid1.subnet.oc1..subnet"
        )


class TestGetOrCreateSubnet:
    def test_creates_subnet_with_empty_security_list_ids(self):
        from dstack._internal.core.backends.oci import resources

        client = MagicMock()
        client.list_subnets.return_value.data = []
        client.list_subnets.return_value.next_page = None
        client.list_subnets.return_value.has_next_page = False

        resources.get_or_create_subnet(
            "dstack-test-project-default-subnet",
            "ocid1.vcn.oc1..vcn",
            "ocid1.compartment.oc1..compartment",
            client,
        )

        client.create_subnet.assert_called_once()
        details = client.create_subnet.call_args.args[0]
        assert details.security_list_ids == []
        assert details.vcn_id == "ocid1.vcn.oc1..vcn"
        assert details.display_name == "dstack-test-project-default-subnet"

    def test_returns_existing_subnet_without_creating(self):
        from dstack._internal.core.backends.oci import resources

        existing = MagicMock()
        existing.security_list_ids = []
        client = MagicMock()
        client.list_subnets.return_value.data = [existing]
        client.list_subnets.return_value.next_page = None
        client.list_subnets.return_value.has_next_page = False

        result = resources.get_or_create_subnet(
            "dstack-test-project-default-subnet",
            "ocid1.vcn.oc1..vcn",
            "ocid1.compartment.oc1..compartment",
            client,
        )

        assert result is existing
        client.create_subnet.assert_not_called()
        client.update_subnet.assert_not_called()

    def test_existing_subnet_with_security_list_is_updated_to_remove_it(self):
        """
        A subnet created before this fix still has the VCN's default security
        list attached. Since this subnet is dstack-owned infrastructure (not a
        user-supplied resource), it must be updated in place so the NSG becomes
        the sole security boundary, matching subnets created after the fix.
        """
        from dstack._internal.core.backends.oci import resources

        existing = MagicMock()
        existing.id = "ocid1.subnet.oc1..existing"
        existing.security_list_ids = ["ocid1.securitylist.oc1..default"]
        client = MagicMock()
        client.list_subnets.return_value.data = [existing]
        client.list_subnets.return_value.next_page = None
        client.list_subnets.return_value.has_next_page = False
        updated = MagicMock()
        client.update_subnet.return_value.data = updated

        result = resources.get_or_create_subnet(
            "dstack-test-project-default-subnet",
            "ocid1.vcn.oc1..vcn",
            "ocid1.compartment.oc1..compartment",
            client,
        )

        client.create_subnet.assert_not_called()
        client.update_subnet.assert_called_once()
        args, _ = client.update_subnet.call_args
        assert args[0] == "ocid1.subnet.oc1..existing"
        assert args[1].security_list_ids == []
        assert result is updated


class TestUpdateSecurityGroupRulesForRunnerInstances:
    def test_adds_ssh_ingress_and_egress_rules(self):
        from dstack._internal.core.backends.oci import resources

        client = MagicMock()
        client.list_network_security_group_security_rules.return_value.data = []
        client.list_network_security_group_security_rules.return_value.next_page = None
        client.list_network_security_group_security_rules.return_value.has_next_page = False

        resources.update_security_group_rules_for_runner_instances(
            "ocid1.nsg.oc1..managed", client
        )

        client.add_network_security_group_security_rules.assert_called_once()
        (_, details), _ = client.add_network_security_group_security_rules.call_args
        rules = details.security_rules
        directions = {rule.direction for rule in rules}
        assert (
            oci.core.models.AddSecurityRuleDetails.DIRECTION_INGRESS in directions
        )
        assert oci.core.models.AddSecurityRuleDetails.DIRECTION_EGRESS in directions

        ssh_rules = [
            rule
            for rule in rules
            if rule.direction == oci.core.models.AddSecurityRuleDetails.DIRECTION_INGRESS
            and rule.source_type
            == oci.core.models.AddSecurityRuleDetails.SOURCE_TYPE_CIDR_BLOCK
        ]
        assert len(ssh_rules) == 1
        assert ssh_rules[0].source == "0.0.0.0/0"
        assert ssh_rules[0].tcp_options.destination_port_range.min == 22
        assert ssh_rules[0].tcp_options.destination_port_range.max == 22

        egress_rules = [
            rule
            for rule in rules
            if rule.direction == oci.core.models.AddSecurityRuleDetails.DIRECTION_EGRESS
        ]
        assert len(egress_rules) == 1
        assert egress_rules[0].destination == "0.0.0.0/0"
        assert (
            egress_rules[0].destination_type
            == oci.core.models.AddSecurityRuleDetails.DESTINATION_TYPE_CIDR_BLOCK
        )

        intra_group_rules = [
            rule
            for rule in rules
            if rule.direction == oci.core.models.AddSecurityRuleDetails.DIRECTION_INGRESS
            and rule.source_type
            == oci.core.models.AddSecurityRuleDetails.SOURCE_TYPE_NETWORK_SECURITY_GROUP
        ]
        assert len(intra_group_rules) == 1
        assert intra_group_rules[0].source == "ocid1.nsg.oc1..managed"
