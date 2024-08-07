import json
from operator import itemgetter
from unittest.mock import Mock, patch

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.oci import region as oci_region
from dstack._internal.core.errors import BackendAuthError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
from dstack._internal.server.models import BackendModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_backend,
    create_project,
    create_user,
    get_auth_headers,
)

client = TestClient(app)


FAKE_OCI_CLIENT_CREDS = {
    "type": "client",
    "user": "ocid1.user.oc1..aaaaaaaa",
    "tenancy": "ocid1.tenancy.oc1..aaaaaaaa",
    "key_content": (
        "-----BEGIN PRIVATE KEY-----\n"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "-----END PRIVATE KEY-----"
    ),
    "fingerprint": "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00",
    "region": "me-dubai-1",
}
SAMPLE_OCI_COMPARTMENT_ID = "ocid1.compartment.oc1..aaaaaaaa"
SAMPLE_OCI_SUBSCRIBED_REGIONS = oci_region.SubscribedRegions(
    names={"me-dubai-1", "eu-frankfurt-1"}, home_region_name="eu-frankfurt-1"
)
SAMPLE_OCI_SUBNETS = {
    "me-dubai-1": "ocid1.subnet.oc1.me-dubai-1.aaaaaaaa",
    "eu-frankfurt-1": "ocid1.subnet.oc1.eu-frankfurt-1.aaaaaaaa",
}


class TestListBackendTypes:
    def test_returns_backend_types(self):
        response = client.post("/api/backends/list_types")
        assert response.status_code == 200, response.json()
        assert response.json() == [
            "aws",
            "azure",
            "cudo",
            "datacrunch",
            "gcp",
            "kubernetes",
            "lambda",
            "nebius",
            "oci",
            "runpod",
            "tensordock",
            "vastai",
        ]


class TestGetBackendConfigValuesAWS:
    @pytest.mark.asyncio
    async def test_returns_initial_config(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {"type": "aws"}
        with patch(
            "dstack._internal.core.backends.aws.auth.default_creds_available"
        ) as default_creds_available_mock:
            default_creds_available_mock.return_value = False
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            default_creds_available_mock.assert_called()
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "aws",
            "default_creds": False,
            "regions": None,
        }

    @pytest.mark.asyncio
    async def test_returns_invalid_credentials(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
        }
        with patch(
            "dstack._internal.core.backends.aws.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.aws.auth.authenticate"
        ) as authenticate_mock:
            authenticate_mock.side_effect = BackendAuthError()
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            default_creds_available_mock.assert_called()
            authenticate_mock.assert_called()
        assert response.status_code == 400
        assert response.json() == {
            "detail": [
                {
                    "code": "invalid_credentials",
                    "msg": "Invalid credentials",
                    "fields": ["creds", "access_key"],
                },
                {
                    "code": "invalid_credentials",
                    "msg": "Invalid credentials",
                    "fields": ["creds", "secret_key"],
                },
            ]
        }

    @pytest.mark.asyncio
    async def test_returns_config_on_valid_creds(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
        }
        with patch(
            "dstack._internal.core.backends.aws.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.aws.auth.authenticate"
        ) as authenticate_mock, patch(
            "dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"
        ):
            default_creds_available_mock.return_value = True
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            default_creds_available_mock.assert_called()
            authenticate_mock.assert_called()
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "aws",
            "default_creds": True,
            "regions": {
                "selected": [
                    "us-east-1",
                    "us-east-2",
                    "us-west-1",
                    "us-west-2",
                    "ap-southeast-1",
                    "ca-central-1",
                    "eu-central-1",
                    "eu-west-1",
                    "eu-west-2",
                    "eu-west-3",
                    "eu-north-1",
                ],
                "values": [
                    {"label": "us-east-1", "value": "us-east-1"},
                    {"label": "us-east-2", "value": "us-east-2"},
                    {"label": "us-west-1", "value": "us-west-1"},
                    {"label": "us-west-2", "value": "us-west-2"},
                    {"label": "ap-southeast-1", "value": "ap-southeast-1"},
                    {"label": "ca-central-1", "value": "ca-central-1"},
                    {"label": "eu-central-1", "value": "eu-central-1"},
                    {"label": "eu-west-1", "value": "eu-west-1"},
                    {"label": "eu-west-2", "value": "eu-west-2"},
                    {"label": "eu-west-3", "value": "eu-west-3"},
                    {"label": "eu-north-1", "value": "eu-north-1"},
                ],
            },
        }


class TestGetBackendConfigValuesAzure:
    @pytest.mark.asyncio
    async def test_returns_initial_config(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {"type": "azure"}
        with patch(
            "dstack._internal.core.backends.azure.auth.default_creds_available"
        ) as default_creds_available_mock:
            default_creds_available_mock.return_value = False
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            default_creds_available_mock.assert_called()
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "azure",
            "default_creds": False,
            "tenant_id": None,
            "subscription_id": None,
            "locations": None,
        }

    @pytest.mark.asyncio
    async def test_returns_invalid_credentials(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "azure",
            "creds": {
                "type": "client",
                "tenant_id": "1234",
                "client_id": "1234",
                "client_secret": "1234",
            },
        }
        with patch(
            "dstack._internal.core.backends.azure.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.azure.auth.authenticate"
        ) as authenticate_mock:
            default_creds_available_mock.return_value = False
            authenticate_mock.side_effect = BackendAuthError()
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            default_creds_available_mock.assert_called()
            authenticate_mock.assert_called()
        assert response.status_code == 400
        assert response.json() == {
            "detail": [
                {
                    "code": "invalid_credentials",
                    "msg": "Invalid credentials",
                    "fields": ["creds", "tenant_id"],
                },
                {
                    "code": "invalid_credentials",
                    "msg": "Invalid credentials",
                    "fields": ["creds", "client_id"],
                },
                {
                    "code": "invalid_credentials",
                    "msg": "Invalid credentials",
                    "fields": ["creds", "client_secret"],
                },
            ]
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "body",
        [
            {
                "type": "azure",
                "creds": {
                    "type": "client",
                    "client_id": "1234",
                    "client_secret": "1234",
                },
                "tenant_id": "test_tenant",
            },
            {
                "type": "azure",
                "creds": {
                    "type": "client",
                    "tenant_id": "test_tenant",
                    "client_id": "1234",
                    "client_secret": "1234",
                },
            },
        ],
    )
    async def test_returns_config_on_valid_creds(self, test_db, session: AsyncSession, body):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        with patch(
            "dstack._internal.core.backends.azure.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.azure.auth.authenticate"
        ) as authenticate_mock, patch(
            "azure.mgmt.subscription.SubscriptionClient"
        ) as SubscriptionClientMock:
            default_creds_available_mock.return_value = False
            authenticate_mock.return_value = None, "test_tenant"
            client_mock = SubscriptionClientMock.return_value
            tenant_mock = Mock()
            tenant_mock.tenant_id = "test_tenant"
            client_mock.tenants.list.return_value = [tenant_mock]
            subscription_mock = Mock()
            subscription_mock.subscription_id = "test_subscription"
            subscription_mock.display_name = "Subscription"
            client_mock.subscriptions.list.return_value = [subscription_mock]
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200
        assert response.json() == {
            "type": "azure",
            "default_creds": False,
            "tenant_id": {
                "selected": "test_tenant",
                "values": [
                    {
                        "value": "test_tenant",
                        "label": "test_tenant",
                    }
                ],
            },
            "subscription_id": {
                "selected": "test_subscription",
                "values": [
                    {
                        "value": "test_subscription",
                        "label": "Subscription (test_subscription)",
                    }
                ],
            },
            "locations": {
                "selected": [
                    "centralus",
                    "eastus",
                    "eastus2",
                    "southcentralus",
                    "westus2",
                    "westus3",
                    "canadacentral",
                    "francecentral",
                    "germanywestcentral",
                    "northeurope",
                    "swedencentral",
                    "uksouth",
                    "westeurope",
                    "southeastasia",
                    "eastasia",
                    "brazilsouth",
                ],
                "values": [
                    {"value": "centralus", "label": "centralus"},
                    {"value": "eastus", "label": "eastus"},
                    {"value": "eastus2", "label": "eastus2"},
                    {"value": "southcentralus", "label": "southcentralus"},
                    {"value": "westus2", "label": "westus2"},
                    {"value": "westus3", "label": "westus3"},
                    {"value": "canadacentral", "label": "canadacentral"},
                    {"value": "francecentral", "label": "francecentral"},
                    {"value": "germanywestcentral", "label": "germanywestcentral"},
                    {"value": "northeurope", "label": "northeurope"},
                    {"value": "swedencentral", "label": "swedencentral"},
                    {"value": "uksouth", "label": "uksouth"},
                    {"value": "westeurope", "label": "westeurope"},
                    {"value": "southeastasia", "label": "southeastasia"},
                    {"value": "eastasia", "label": "eastasia"},
                    {"value": "brazilsouth", "label": "brazilsouth"},
                ],
            },
        }


class TestGetBackendConfigValuesGCP:
    @pytest.mark.asyncio
    async def test_returns_initial_config(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {"type": "gcp"}
        with patch("dstack._internal.core.backends.gcp.auth.default_creds_available") as m:
            m.return_value = True
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "gcp",
            "default_creds": True,
            "project_id": None,
            "regions": None,
        }

    @pytest.mark.asyncio
    async def test_returns_invalid_credentials(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "gcp",
            "creds": {
                "type": "service_account",
                "filename": "1234",
                "data": "1234",
            },
        }
        with patch(
            "dstack._internal.core.backends.gcp.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.gcp.auth.authenticate"
        ) as authenticate_mock:
            default_creds_available_mock.return_value = False
            authenticate_mock.side_effect = BackendAuthError()
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            authenticate_mock.assert_called()
        assert response.status_code == 400
        assert response.json() == {
            "detail": [
                {
                    "code": "invalid_credentials",
                    "msg": "Invalid credentials",
                    "fields": ["creds", "data"],
                },
            ]
        }

    @pytest.mark.asyncio
    async def test_returns_config_on_valid_creds(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "gcp",
            "creds": {
                "type": "service_account",
                "filename": "1234",
                "data": "1234",
            },
            "project_id": "test_project",
        }
        with patch(
            "dstack._internal.core.backends.gcp.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.gcp.auth.authenticate"
        ) as authenticate_mock, patch(
            "dstack._internal.core.backends.gcp.resources.check_vpc"
        ) as check_vpc_mock:
            default_creds_available_mock.return_value = False
            authenticate_mock.return_value = {}, "test_project"
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            authenticate_mock.assert_called()
            check_vpc_mock.assert_called()
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "gcp",
            "default_creds": False,
            "project_id": {
                "selected": "test_project",
                "values": [
                    {
                        "value": "test_project",
                        "label": "test_project",
                    }
                ],
            },
            "regions": {
                "selected": [
                    "northamerica-northeast1",
                    "northamerica-northeast2",
                    "us-central1",
                    "us-east1",
                    "us-east4",
                    "us-east5",
                    "us-south1",
                    "us-west1",
                    "us-west2",
                    "us-west3",
                    "us-west4",
                    "southamerica-east1",
                    "southamerica-west1",
                    "europe-central2",
                    "europe-north1",
                    "europe-southwest1",
                    "europe-west1",
                    "europe-west2",
                    "europe-west3",
                    "europe-west4",
                    "europe-west6",
                    "europe-west8",
                    "europe-west9",
                    "asia-east1",
                    "asia-east2",
                    "asia-northeast1",
                    "asia-northeast2",
                    "asia-northeast3",
                    "asia-south1",
                    "asia-south2",
                    "asia-southeast1",
                    "asia-southeast2",
                    "me-west1",
                    "australia-southeast1",
                    "australia-southeast2",
                ],
                "values": [
                    {
                        "value": "northamerica-northeast1",
                        "label": "northamerica-northeast1",
                    },
                    {
                        "value": "northamerica-northeast2",
                        "label": "northamerica-northeast2",
                    },
                    {"value": "us-central1", "label": "us-central1"},
                    {"value": "us-east1", "label": "us-east1"},
                    {"value": "us-east4", "label": "us-east4"},
                    {"value": "us-east5", "label": "us-east5"},
                    {"value": "us-south1", "label": "us-south1"},
                    {"value": "us-west1", "label": "us-west1"},
                    {"value": "us-west2", "label": "us-west2"},
                    {"value": "us-west3", "label": "us-west3"},
                    {"value": "us-west4", "label": "us-west4"},
                    {"value": "southamerica-east1", "label": "southamerica-east1"},
                    {"value": "southamerica-west1", "label": "southamerica-west1"},
                    {"value": "europe-central2", "label": "europe-central2"},
                    {"value": "europe-north1", "label": "europe-north1"},
                    {"value": "europe-southwest1", "label": "europe-southwest1"},
                    {"value": "europe-west1", "label": "europe-west1"},
                    {"value": "europe-west2", "label": "europe-west2"},
                    {"value": "europe-west3", "label": "europe-west3"},
                    {"value": "europe-west4", "label": "europe-west4"},
                    {"value": "europe-west6", "label": "europe-west6"},
                    {"value": "europe-west8", "label": "europe-west8"},
                    {"value": "europe-west9", "label": "europe-west9"},
                    {"value": "asia-east1", "label": "asia-east1"},
                    {"value": "asia-east2", "label": "asia-east2"},
                    {"value": "asia-northeast1", "label": "asia-northeast1"},
                    {"value": "asia-northeast2", "label": "asia-northeast2"},
                    {"value": "asia-northeast3", "label": "asia-northeast3"},
                    {"value": "asia-south1", "label": "asia-south1"},
                    {"value": "asia-south2", "label": "asia-south2"},
                    {"value": "asia-southeast1", "label": "asia-southeast1"},
                    {"value": "asia-southeast2", "label": "asia-southeast2"},
                    {"value": "me-west1", "label": "me-west1"},
                    {"value": "australia-southeast1", "label": "australia-southeast1"},
                    {"value": "australia-southeast2", "label": "australia-southeast2"},
                ],
            },
        }


class TestGetBackendConfigValuesLambda:
    @pytest.mark.asyncio
    async def test_returns_initial_config(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {"type": "lambda"}
        response = client.post(
            "/api/backends/config_values",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "lambda",
            "regions": None,
        }

    @pytest.mark.asyncio
    async def test_returns_invalid_credentials(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "lambda",
            "creds": {
                "type": "api_key",
                "api_key": "1234",
            },
        }
        with patch("dstack._internal.core.backends.lambdalabs.api_client.LambdaAPIClient") as m:
            m.return_value.validate_api_key.return_value = False
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            m.return_value.validate_api_key.assert_called()
        assert response.status_code == 400, response.json()
        assert response.json() == {
            "detail": [
                {
                    "code": "invalid_credentials",
                    "msg": "Invalid credentials",
                    "fields": ["creds", "api_key"],
                },
            ]
        }

    @pytest.mark.asyncio
    async def test_returns_config_on_valid_creds(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "lambda",
            "creds": {
                "type": "api_key",
                "api_key": "1234",
            },
        }
        with patch("dstack._internal.core.backends.lambdalabs.api_client.LambdaAPIClient") as m:
            m.return_value.validate_api_key.return_value = True
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            m.return_value.validate_api_key.assert_called()
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "lambda",
            "regions": {
                "selected": ["us-east-1"],
                "values": [
                    {"value": "us-south-1", "label": "us-south-1"},
                    {"value": "us-west-2", "label": "us-west-2"},
                    {"value": "us-west-1", "label": "us-west-1"},
                    {"value": "us-midwest-1", "label": "us-midwest-1"},
                    {"value": "us-west-3", "label": "us-west-3"},
                    {"value": "us-east-1", "label": "us-east-1"},
                    {
                        "value": "australia-southeast-1",
                        "label": "australia-southeast-1",
                    },
                    {"value": "europe-central-1", "label": "europe-central-1"},
                    {"value": "asia-south-1", "label": "asia-south-1"},
                    {"value": "me-west-1", "label": "me-west-1"},
                    {"value": "europe-south-1", "label": "europe-south-1"},
                    {"value": "asia-northeast-1", "label": "asia-northeast-1"},
                ],
            },
        }


class TestGetBackendConfigValuesOCI:
    @pytest.mark.asyncio
    async def test_returns_initial_config(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {"type": "oci"}
        with patch(
            "dstack._internal.core.backends.oci.auth.default_creds_available"
        ) as default_creds_available_mock:
            default_creds_available_mock.return_value = False
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            default_creds_available_mock.assert_called()
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "oci",
            "default_creds": False,
            "regions": None,
            "compartment_id": None,
        }

    @pytest.mark.asyncio
    async def test_returns_invalid_credentials(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "oci",
            "creds": FAKE_OCI_CLIENT_CREDS,
        }
        with patch(
            "dstack._internal.core.backends.oci.auth.default_creds_available"
        ) as default_creds_available_mock:
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            default_creds_available_mock.assert_called()
        assert response.status_code == 400
        error = response.json()["detail"][0]
        assert error["code"] == "invalid_credentials"
        assert error["msg"].startswith("Invalid credentials")

    @pytest.mark.asyncio
    async def test_returns_config_on_valid_creds(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        body = {
            "type": "oci",
            "creds": FAKE_OCI_CLIENT_CREDS,
        }
        with patch(
            "dstack._internal.core.backends.oci.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.server.services.backends.configurators.oci.get_subscribed_regions"
        ) as get_regions_mock:
            default_creds_available_mock.return_value = True
            get_regions_mock.return_value = SAMPLE_OCI_SUBSCRIBED_REGIONS
            response = client.post(
                "/api/backends/config_values",
                headers=get_auth_headers(user.token),
                json=body,
            )
            default_creds_available_mock.assert_called()
            get_regions_mock.assert_called()
        body = response.json()
        body["regions"]["selected"].sort()
        body["regions"]["values"].sort(key=itemgetter("value"))
        assert response.status_code == 200, response.json()
        assert body == {
            "type": "oci",
            "default_creds": True,
            "regions": {
                "selected": ["eu-frankfurt-1", "me-dubai-1"],
                "values": [
                    {"label": "eu-frankfurt-1", "value": "eu-frankfurt-1"},
                    {"label": "me-dubai-1", "value": "me-dubai-1"},
                ],
            },
            "compartment_id": None,
        }


class TestCreateBackend:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/backends/create",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_creates_aws_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-west-1"],
        }
        with patch(
            "dstack._internal.core.backends.aws.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.aws.auth.authenticate"
        ), patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"):
            default_creds_available_mock.return_value = False
            response = client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_creates_gcp_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "gcp",
            "creds": {
                "type": "service_account",
                "filename": "1234",
                "data": "1234",
            },
            "project_id": "test_project",
            "regions": ["us-east1"],
        }
        with patch(
            "dstack._internal.core.backends.gcp.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.gcp.auth.authenticate"
        ) as authenticate_mock, patch(
            "dstack._internal.core.backends.gcp.resources.check_vpc"
        ) as check_vpc_mock:
            default_creds_available_mock.return_value = False
            credentials_mock = Mock()
            authenticate_mock.return_value = credentials_mock, "test_project"
            response = client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
            check_vpc_mock.assert_called()
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_creates_lambda_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "lambda",
            "creds": {
                "type": "api_key",
                "api_key": "1234",
            },
            "regions": ["asd"],
        }
        with patch("dstack._internal.core.backends.lambdalabs.api_client.LambdaAPIClient") as m:
            m.return_value.validate_api_key.return_value = True
            response = client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
            m.return_value.validate_api_key.assert_called()
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_creates_oci_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "oci",
            "creds": FAKE_OCI_CLIENT_CREDS,
        }
        with patch(
            "dstack._internal.core.backends.oci.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.server.services.backends.configurators.oci.get_subscribed_regions"
        ) as get_regions_mock, patch(
            "dstack._internal.server.services.backends.configurators.oci._create_resources"
        ) as create_resources_mock:
            default_creds_available_mock.return_value = False
            get_regions_mock.return_value = SAMPLE_OCI_SUBSCRIBED_REGIONS
            create_resources_mock.return_value = SAMPLE_OCI_COMPARTMENT_ID, SAMPLE_OCI_SUBNETS
            response = client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_not_creates_oci_backend_if_regions_not_subscribed(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "oci",
            "creds": FAKE_OCI_CLIENT_CREDS,
            "regions": ["me-dubai-1", "eu-frankfurt-1", "us-ashburn-1"],
        }
        with patch(
            "dstack._internal.core.backends.oci.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.server.services.backends.configurators.oci.get_subscribed_regions"
        ) as get_regions_mock:
            default_creds_available_mock.return_value = False
            # us-ashburn-1 not subscribed
            get_regions_mock.return_value = SAMPLE_OCI_SUBSCRIBED_REGIONS
            response = client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 400, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 0

    @pytest.mark.asyncio
    async def test_create_azure_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "azure",
            "creds": {
                "type": "client",
                "tenant_id": "test_tenant",
                "client_id": "1234",
                "client_secret": "1234",
            },
            "tenant_id": "test_tenant",
            "subscription_id": "test_subscription",
            "locations": ["eastus"],
        }
        with patch(
            "dstack._internal.core.backends.azure.auth.authenticate"
        ) as authenticate_mock, patch(
            "azure.mgmt.subscription.SubscriptionClient"
        ) as SubscriptionClientMock, patch(
            "azure.mgmt.resource.ResourceManagementClient"
        ) as ResourceManagementClientMock, patch(
            "azure.mgmt.network.NetworkManagementClient"
        ) as NetworkManagementClientMock:
            authenticate_mock.return_value = None, "test_tenant"
            subscription_client_mock = SubscriptionClientMock.return_value
            tenant_mock = Mock()
            tenant_mock.tenant_id = "test_tenant"
            subscription_client_mock.tenants.list.return_value = [tenant_mock]
            subscription_mock = Mock()
            subscription_mock.subscription_id = "test_subscription"
            subscription_mock.display_name = "Subscription"
            subscription_client_mock.subscriptions.list.return_value = [subscription_mock]
            resource_client_mock = ResourceManagementClientMock.return_value
            resource_group_mock = Mock()
            resource_group_mock.name = "test_resource_group"
            resource_client_mock.resource_groups.create_or_update.return_value = (
                resource_group_mock
            )
            response = client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
            authenticate_mock.assert_called()
            SubscriptionClientMock.assert_called()
            ResourceManagementClientMock.assert_called()
            NetworkManagementClientMock.assert_called()
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_returns_400_if_backend_exists(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-west-1"],
        }
        with patch(
            "dstack._internal.core.backends.aws.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.aws.auth.authenticate"
        ), patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"):
            default_creds_available_mock.return_value = False
            response = client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1
        with patch(
            "dstack._internal.core.backends.aws.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.aws.auth.authenticate"
        ) as authenticate_mock:  # noqa: F841
            default_creds_available_mock.return_value = False
            response = client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 400, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1


class TestUpdateBackend:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/backends/update",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_updates_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(
            session=session, project_id=project.id, config={"regions": ["us-west-1"]}
        )
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-east-1"],
        }
        with patch(
            "dstack._internal.core.backends.aws.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.aws.auth.authenticate"
        ), patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"):
            default_creds_available_mock.return_value = False
            response = client.post(
                f"/api/project/{project.name}/backends/update",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        await session.refresh(backend)
        assert json.loads(backend.config)["regions"] == ["us-east-1"]

    @pytest.mark.asyncio
    async def test_returns_400_if_backend_does_not_exist(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-east-1"],
        }
        response = client.post(
            f"/api/project/{project.name}/backends/update",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 400


class TestDeleteBackends:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/backends/delete",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_deletes_backends(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session=session, project_id=project.id)
        response = client.post(
            f"/api/project/{project.name}/backends/delete",
            headers=get_auth_headers(user.token),
            json={"backends_names": [backend.type.value]},
        )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 0


class TestGetConfigInfo:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        backend = await create_backend(session=session, project_id=project.id)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/backends/{backend.type.value}/config_info",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_config_info(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        backend = await create_backend(session=session, project_id=project.id)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
            f"/api/project/{project.name}/backends/{backend.type.value}/config_info",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "aws",
            "regions": json.loads(backend.config)["regions"],
            "vpc_name": None,
            "vpc_ids": None,
            "default_vpcs": None,
            "public_ips": None,
            "creds": json.loads(backend.auth),
        }


class TestCreateBackendYAML:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/backends/create_yaml",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_creates_aws_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        config_dict = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-west-1"],
        }
        body = {"config_yaml": yaml.dump(config_dict)}
        with patch(
            "dstack._internal.core.backends.aws.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.aws.auth.authenticate"
        ), patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"):
            default_creds_available_mock.return_value = False
            response = client.post(
                f"/api/project/{project.name}/backends/create_yaml",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_creates_oci_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        config_dict = {
            "type": "oci",
            "creds": FAKE_OCI_CLIENT_CREDS,
        }
        body = {"config_yaml": yaml.dump(config_dict)}
        with patch(
            "dstack._internal.core.backends.oci.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.server.services.backends.configurators.oci.get_subscribed_regions"
        ) as get_regions_mock, patch(
            "dstack._internal.server.services.backends.configurators.oci._create_resources"
        ) as create_resources_mock:
            default_creds_available_mock.return_value = False
            get_regions_mock.return_value = SAMPLE_OCI_SUBSCRIBED_REGIONS
            create_resources_mock.return_value = SAMPLE_OCI_COMPARTMENT_ID, SAMPLE_OCI_SUBNETS
            response = client.post(
                f"/api/project/{project.name}/backends/create_yaml",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1


class TestUpdateBackendYAML:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/backends/update_yaml",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_updates_aws_backend(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(
            session=session,
            project_id=project.id,
            backend_type=BackendType.AWS,
            config={"regions": ["us-west-1"]},
        )
        config_dict = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-east-1"],
        }
        body = {"config_yaml": yaml.dump(config_dict)}
        with patch(
            "dstack._internal.core.backends.aws.auth.default_creds_available"
        ) as default_creds_available_mock, patch(
            "dstack._internal.core.backends.aws.auth.authenticate"
        ), patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"):
            default_creds_available_mock.return_value = False
            response = client.post(
                f"/api/project/{project.name}/backends/update_yaml",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        await session.refresh(backend)
        assert json.loads(backend.config)["regions"] == ["us-east-1"]


class TestGetConfigYAML:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_admin(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        await create_backend(
            session=session,
            project_id=project.id,
            backend_type=BackendType.AWS,
            config={"regions": ["us-west-1"]},
        )
        response = client.post(
            f"/api/project/{project.name}/backends/aws/get_yaml",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_config_yaml(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        auth = {
            "type": "access_key",
            "access_key": "test_access_key",
            "secret_key": "test_secret_key",
        }
        config = {"regions": ["us-west-1"]}
        await create_backend(
            session=session,
            project_id=project.id,
            backend_type=BackendType.AWS,
            config=config,
            auth=auth,
        )
        response = client.post(
            f"/api/project/{project.name}/backends/aws/get_yaml",
            headers=get_auth_headers(user.token),
            json={},
        )
        expected_config_yaml = (
            "type: aws\n"
            "regions: [us-west-1]\n"
            "creds:\n"
            "  type: access_key\n"
            "  access_key: test_access_key\n"
            "  secret_key: test_secret_key\n"
        )
        assert response.status_code == 200
        assert response.json() == {"name": "aws", "config_yaml": expected_config_yaml}
