from unittest.mock import Mock, patch

import pytest

from dstack._internal.core.backends.gcp.compute import GCPCompute
from dstack._internal.core.backends.gcp.models import GCPConfig, GCPServiceAccountCreds
from dstack._internal.core.errors import ComputeResourceNotFoundError


class _StopExecution(Exception):
    """Raised to stop `create_*` right after the firewall guard is evaluated."""


def _make_compute(create_firewall_rules=None, vpc_project_id=None) -> GCPCompute:
    config = GCPConfig(
        project_id="test-project",
        vpc_project_id=vpc_project_id,
        create_firewall_rules=create_firewall_rules,
        creds=GCPServiceAccountCreds(data="creds"),
    )
    # Bypass __init__ to avoid authenticating and creating real GCP clients.
    compute = GCPCompute.__new__(GCPCompute)
    compute.config = config
    compute.firewalls_client = Mock()
    return compute


def _run_create_instance(compute: GCPCompute):
    instance_offer = Mock()
    instance_offer.availability_zones = ["us-west1-a"]
    instance_offer.region = "us-west1"
    instance_offer.instance.resources.disk.size_mib = 102400
    instance_config = Mock()
    instance_config.get_public_keys.return_value = []
    # Stop execution right after the firewall guard block.
    compute._get_vpc_subnet = Mock(side_effect=_StopExecution)
    with (
        patch(
            "dstack._internal.core.backends.gcp.compute.generate_unique_instance_name",
            return_value="instance-name",
        ),
        patch(
            "dstack._internal.core.backends.gcp.resources.create_runner_firewall_rules"
        ) as create_rules_mock,
        pytest.raises(_StopExecution),
    ):
        compute.create_instance(instance_offer, instance_config, None)
    return create_rules_mock


def _run_create_gateway(compute: GCPCompute):
    configuration = Mock()
    configuration.region = "us-west1"
    compute.regions_client = Mock()
    # Empty region list makes create_gateway raise right after the firewall guard.
    compute.regions_client.list.return_value = []
    with (
        patch(
            "dstack._internal.core.backends.gcp.resources.create_gateway_firewall_rules"
        ) as create_rules_mock,
        pytest.raises(ComputeResourceNotFoundError),
    ):
        compute.create_gateway(configuration)
    return create_rules_mock


class TestCreateFirewallRules:
    def test_runner_firewall_rules_created_by_default(self):
        create_rules_mock = _run_create_instance(_make_compute())
        create_rules_mock.assert_called_once()

    def test_runner_firewall_rules_created_when_explicitly_enabled(self):
        create_rules_mock = _run_create_instance(_make_compute(create_firewall_rules=True))
        create_rules_mock.assert_called_once()

    def test_runner_firewall_rules_skipped_when_disabled(self):
        create_rules_mock = _run_create_instance(_make_compute(create_firewall_rules=False))
        create_rules_mock.assert_not_called()

    def test_gateway_firewall_rules_created_by_default(self):
        create_rules_mock = _run_create_gateway(_make_compute())
        create_rules_mock.assert_called_once()

    def test_gateway_firewall_rules_created_when_explicitly_enabled(self):
        create_rules_mock = _run_create_gateway(_make_compute(create_firewall_rules=True))
        create_rules_mock.assert_called_once()

    def test_gateway_firewall_rules_not_affected_by_create_firewall_rules(self):
        # `create_firewall_rules` only gates the runner (instance) firewall rule, not the
        # gateway one - gateways are meant to be internet-reachable and are always auto-managed,
        # consistent with how gateway security groups/NSGs are handled on AWS/Azure/OCI.
        create_rules_mock = _run_create_gateway(_make_compute(create_firewall_rules=False))
        create_rules_mock.assert_called_once()
