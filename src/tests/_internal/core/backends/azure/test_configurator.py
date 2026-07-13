from unittest.mock import Mock, patch

import pytest

from dstack._internal.core.backends.azure.configurator import AzureConfigurator
from dstack._internal.core.backends.azure.models import (
    AzureBackendConfigWithCreds,
    AzureClientCreds,
)
from dstack._internal.core.errors import (
    BackendAuthError,
    BackendInvalidCredentialsError,
    ServerClientError,
)


class TestAzureConfigurator:
    def test_validate_config_valid(self):
        config = AzureBackendConfigWithCreds(
            creds=AzureClientCreds(
                tenant_id="valid",
                client_id="valid",
                client_secret="valid",
            ),
            tenant_id="ten1",
            subscription_id="sub1",
            regions=["eastus"],
        )
        with (
            patch("dstack._internal.core.backends.azure.auth.authenticate") as authenticate_mock,
            patch("azure.mgmt.subscription.SubscriptionClient") as SubscriptionClientMock,
        ):
            authenticate_mock.return_value = Mock(), Mock()
            subcription_client_mock = SubscriptionClientMock.return_value
            subcription_client_mock.tenants.list.return_value = [Mock(tenant_id="ten1")]
            subcription_client_mock.subscriptions.list.return_value = [
                Mock(subscription_id="sub1")
            ]
            AzureConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = AzureBackendConfigWithCreds(
            creds=AzureClientCreds(
                tenant_id="invalid",
                client_id="invalid",
                client_secret="invalid",
            ),
            tenant_id="invalid",
            subscription_id="invalid",
            regions=["eastus"],
        )
        with (
            patch("dstack._internal.core.backends.azure.auth.authenticate") as mock_authenticate,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            mock_authenticate.side_effect = BackendAuthError()
            AzureConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [
            ["creds", "tenant_id"],
            ["creds", "client_id"],
            ["creds", "client_secret"],
        ]


class TestCheckConfigVpc:
    def _make_config(self, **kwargs):
        return AzureBackendConfigWithCreds(
            creds=AzureClientCreds(tenant_id="t", client_id="c", client_secret="s"),
            tenant_id="ten1",
            subscription_id="sub1",
            **kwargs,
        )

    def _check(self, config):
        with (
            patch("azure.mgmt.network.NetworkManagementClient"),
            patch(
                "dstack._internal.core.backends.azure.compute.get_resource_group_network_subnet_or_error"
            ),
        ):
            AzureConfigurator()._check_config_vpc(config, Mock())

    def test_public_ips_false_requires_network_config(self):
        config = self._make_config(regions=["westeurope"], public_ips=False)
        with pytest.raises(ServerClientError, match="`vpc_ids` or `subnet_ids` must be specified"):
            AzureConfigurator()._check_config_vpc(config, Mock())

    def test_public_ips_false_with_vpc_ids_ok(self):
        config = self._make_config(
            regions=["westeurope"], public_ips=False, vpc_ids={"westeurope": "rg/net"}
        )
        self._check(config)

    def test_public_ips_false_with_subnet_ids_ok(self):
        config = self._make_config(
            regions=["westeurope"], public_ips=False, subnet_ids={"westeurope": "rg/net/subnet"}
        )
        self._check(config)

    def test_overlap_raises(self):
        config = self._make_config(
            regions=["westeurope", "eastus"],
            vpc_ids={"westeurope": "rg/net", "eastus": "rg/net2"},
            subnet_ids={"westeurope": "rg/net/subnet"},
        )
        with pytest.raises(ServerClientError, match="westeurope"):
            AzureConfigurator()._check_config_vpc(config, Mock())

    def test_uncovered_region_raises_with_vpc_ids(self):
        config = self._make_config(
            regions=["westeurope", "eastus"],
            vpc_ids={"westeurope": "rg/net"},
        )
        with pytest.raises(ServerClientError, match="eastus"):
            AzureConfigurator()._check_config_vpc(config, Mock())

    def test_uncovered_region_raises_with_subnet_ids(self):
        config = self._make_config(
            regions=["westeurope", "eastus"],
            subnet_ids={"westeurope": "rg/net/subnet"},
        )
        with pytest.raises(ServerClientError, match="eastus"):
            AzureConfigurator()._check_config_vpc(config, Mock())

    def test_mixed_vpc_and_subnet_ids_covers_all_regions(self):
        config = self._make_config(
            regions=["westeurope", "eastus"],
            vpc_ids={"westeurope": "rg/net"},
            subnet_ids={"eastus": "rg/net/subnet"},
        )
        self._check(config)


class TestCreateBackendNetworkSecurityGroup:
    def _make_config(self, **kwargs):
        return AzureBackendConfigWithCreds(
            creds=AzureClientCreds(tenant_id="t", client_id="c", client_secret="s"),
            tenant_id="ten1",
            subscription_id="sub1",
            resource_group="my-rg",
            regions=["eastus"],
            **kwargs,
        )

    def _create_backend(self, config):
        with (
            patch("dstack._internal.core.backends.azure.auth.authenticate") as authenticate_mock,
            patch(
                "dstack._internal.core.backends.azure.configurator.NetworkManager"
            ) as NetworkManagerMock,
        ):
            authenticate_mock.return_value = Mock(), Mock()
            AzureConfigurator().create_backend("proj", config)
            return NetworkManagerMock.return_value

    def test_creates_instance_nsg_by_default(self):
        network_manager = self._create_backend(self._make_config())
        network_manager.create_network_security_group.assert_called_once()

    def test_skips_instance_nsg_when_configured(self):
        network_manager = self._create_backend(self._make_config(network_security_group="my-nsg"))
        network_manager.create_network_security_group.assert_not_called()
        # The gateway NSG is unaffected and still created.
        network_manager.create_gateway_network_security_group.assert_called_once()
