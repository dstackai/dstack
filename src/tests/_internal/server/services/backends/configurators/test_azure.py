from unittest.mock import Mock, patch

import pytest

from dstack._internal.core.errors import (
    BackendAuthError,
    BackendInvalidCredentialsError,
)
from dstack._internal.core.models.backends.azure import (
    AzureClientCreds,
    AzureConfigInfoWithCreds,
)
from dstack._internal.server.services.backends.configurators.azure import AzureConfigurator


class TestAzureConfigurator:
    def test_validate_config_valid(self):
        config = AzureConfigInfoWithCreds(
            creds=AzureClientCreds(
                tenant_id="valid",
                client_id="valid",
                client_secret="valid",
            ),
            tenant_id="ten1",
            subscription_id="sub1",
            locations=["eastus"],
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
        config = AzureConfigInfoWithCreds(
            creds=AzureClientCreds(
                tenant_id="invalid",
                client_id="invalid",
                client_secret="invalid",
            ),
            tenant_id="invalid",
            subscription_id="invalid",
            locations=["eastus"],
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
