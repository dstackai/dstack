import json
from typing import Dict, List, Optional, Tuple, Union

import google.auth
import google.auth.exceptions
import googleapiclient.discovery
import googleapiclient.errors
from google.cloud import compute_v1, storage
from google.oauth2 import service_account

from dstack._internal.backend.gcp import GCPBackend
from dstack._internal.backend.gcp import auth as gcp_auth
from dstack._internal.backend.gcp import utils as gcp_utils
from dstack._internal.backend.gcp.config import GCPConfig
from dstack._internal.hub.db.models import Backend as DBBackend
from dstack._internal.hub.schemas import (
    BackendElement,
    BackendElementValue,
    BackendMultiElement,
    GCPBackendConfig,
    GCPBackendConfigWithCreds,
    GCPBackendConfigWithCredsPartial,
    GCPBackendCreds,
    GCPBackendValues,
    GCPVPCSubnetBackendElement,
    GCPVPCSubnetBackendElementValue,
)
from dstack._internal.hub.services.backends.base import BackendConfigError, Configurator

LOCATIONS = [
    {
        "name": "North America",
        "regions": [
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
        ],
        "default_region": "us-west1",
        "default_zone": "us-west1-b",
    },
    {
        "name": "South America",
        "regions": [
            "southamerica-east1",
            "southamerica-west1",
        ],
        "default_region": "southamerica-east1",
        "default_zone": "southamerica-east1-b",
    },
    {
        "name": "Europe",
        "regions": [
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
        ],
        "default_region": "europe-west4",
        "default_zone": "europe-west4-a",
    },
    {
        "name": "Asia",
        "regions": [
            "asia-east1",
            "asia-east2",
            "asia-northeast1",
            "asia-northeast2",
            "asia-northeast3",
            "asia-south1",
            "asia-south2",
            "asia-southeast1",
            "asia-southeast2",
        ],
        "default_region": "asia-southeast1",
        "default_zone": "asia-southeast1-b",
    },
    {
        "name": "Middle East",
        "regions": [
            "me-west1",
        ],
        "default_region": "me-west1",
        "default_zone": "me-west1-b",
    },
    {
        "name": "Australia",
        "regions": [
            "australia-southeast1",
            "australia-southeast2",
        ],
        "default_region": "australia-southeast1",
        "default_zone": "australia-southeast1-c",
    },
]
REGIONS = [r for l in LOCATIONS for r in l["regions"]]
DEFAULT_REGION = "us-east1"


class GCPConfigurator(Configurator):
    NAME = "gcp"

    def configure_backend(
        self, backend_config: GCPBackendConfigWithCredsPartial
    ) -> GCPBackendValues:
        backend_values = GCPBackendValues()
        try:
            self.credentials, self.project_id = google.auth.default()
        except google.auth.exceptions.DefaultCredentialsError:
            backend_values.default_credentials = False
        else:
            backend_values.default_credentials = True

        if backend_config.credentials is None:
            return backend_values

        project_credentials = backend_config.credentials.__root__
        if project_credentials.type == "service_account":
            try:
                self._auth(project_credentials.dict())
                storage_client = storage.Client(credentials=self.credentials)
                storage_client.list_buckets(max_results=1)
            except Exception:
                self._raise_invalid_credentials_error(fields=[["credentials", "data"]])
        elif not backend_values.default_credentials:
            self._raise_invalid_credentials_error(fields=[["credentials"]])

        backend_values.bucket_name = self._get_hub_buckets_element(
            selected=backend_config.bucket_name,
        )
        backend_values.regions = self._get_hub_regions_element(
            selected=backend_config.regions or [DEFAULT_REGION],
        )
        backend_values.vpc_subnet = self._get_hub_vpc_subnet_element(
            region=DEFAULT_REGION,
            selected_vpc=backend_config.vpc,
            selected_subnet=backend_config.subnet,
        )
        return backend_values

    def create_backend(
        self, project_name: str, backend_config: GCPBackendConfigWithCreds
    ) -> Tuple[Dict, Dict]:
        auth_data = backend_config.credentials.__root__.dict()
        self._auth(auth_data)
        if backend_config.credentials.__root__.type == "default":
            service_account_email = self._get_or_create_service_account(
                f"{backend_config.bucket_name}-sa"
            )
            self._grant_roles_to_service_account(service_account_email)
            self._check_if_can_create_service_account_key(service_account_email)
            auth_data["service_account_email"] = service_account_email
        config_data = {
            "project": self.project_id,
            "bucket_name": backend_config.bucket_name,
            "regions": backend_config.regions,
            "vpc": backend_config.vpc,
            "subnet": backend_config.subnet,
        }
        return config_data, auth_data

    def get_backend_config(
        self, db_backend: DBBackend, include_creds: bool
    ) -> Union[GCPBackendConfig, GCPBackendConfigWithCreds]:
        config_data = json.loads(db_backend.config)
        regions = config_data.get("regions")
        if regions is None:
            # old regions format
            regions = config_data.get("extra_regions", []) + [config_data.get("region")]
        bucket_name = config_data["bucket_name"]
        vpc = config_data["vpc"]
        subnet = config_data["subnet"]
        if include_creds:
            auth_data = json.loads(db_backend.auth)
            return GCPBackendConfigWithCreds(
                credentials=GCPBackendCreds.parse_obj(auth_data),
                bucket_name=bucket_name,
                regions=regions,
                vpc=vpc,
                subnet=subnet,
            )
        return GCPBackendConfig(
            bucket_name=bucket_name,
            regions=regions,
            vpc=vpc,
            subnet=subnet,
        )

    def get_backend(self, db_backend: DBBackend) -> GCPBackend:
        config_data = json.loads(db_backend.config)
        auth_data = json.loads(db_backend.auth)
        project_id = config_data.get("project")
        regions = config_data.get("regions")
        if regions is None:
            # old regions format
            regions = config_data.get("extra_regions", []) + [config_data.get("region")]
        config = GCPConfig(
            project_id=project_id,
            bucket_name=config_data["bucket_name"],
            regions=regions,
            vpc=config_data["vpc"],
            subnet=config_data["subnet"],
            credentials=auth_data,
        )
        return GCPBackend(config)

    def _get_hub_buckets_element(self, selected: Optional[str] = None) -> BackendElement:
        storage_client = storage.Client(credentials=self.credentials)
        buckets = storage_client.list_buckets()
        bucket_names = [bucket.name for bucket in buckets]
        element = BackendElement(selected=selected)
        for bucket_name in bucket_names:
            element.values.append(BackendElementValue(value=bucket_name, label=bucket_name))
        return element

    def _get_hub_regions_element(
        self,
        selected: List[str],
    ) -> BackendMultiElement:
        element = BackendMultiElement(selected=selected)
        for region_name in REGIONS:
            element.values.append(BackendElementValue(value=region_name, label=region_name))
        return element

    def _get_hub_vpc_subnet_element(
        self,
        region: str,
        selected_vpc: Optional[str],
        selected_subnet: Optional[str],
    ) -> GCPVPCSubnetBackendElement:
        if selected_vpc is None:
            selected_vpc = "default"
        if selected_subnet is None:
            selected_subnet = "default"
        no_preference_vpc_subnet = ("default", "default")
        networks_client = compute_v1.NetworksClient(credentials=self.credentials)
        networks = networks_client.list(project=self.project_id)
        vpc_subnet_list = []
        for network in networks:
            for subnet in network.subnetworks:
                subnet_region = gcp_utils.get_subnet_region(subnet)
                if subnet_region != region:
                    continue
                vpc_subnet_list.append((network.name, gcp_utils.get_subnet_name(subnet)))
        if (selected_vpc, selected_subnet) not in vpc_subnet_list:
            raise BackendConfigError(f"Invalid VPC subnet {selected_vpc, selected_subnet}")
        if (selected_vpc, selected_subnet) != no_preference_vpc_subnet:
            selected = f"{selected_subnet} ({selected_vpc})"
        else:
            selected = f"No preference (default)"
        vpc_subnet_list = sorted(vpc_subnet_list, key=lambda t: t != no_preference_vpc_subnet)
        element = GCPVPCSubnetBackendElement(selected=selected)
        for vpc, subnet in vpc_subnet_list:
            element.values.append(
                GCPVPCSubnetBackendElementValue(
                    vpc=vpc,
                    subnet=subnet,
                    label=f"{subnet} ({vpc})"
                    if (subnet, vpc) != no_preference_vpc_subnet
                    else f"No preference (default)",
                )
            )
        return element

    def _auth(self, credentials_data: Dict):
        if credentials_data["type"] == "service_account":
            service_account_info = json.loads(credentials_data["data"])
            self.credentials = service_account.Credentials.from_service_account_info(
                info=service_account_info
            )
            self.project_id = self.credentials.project_id
        else:
            self.credentials, self.project_id = google.auth.default()

    def _get_or_create_service_account(self, name: str) -> str:
        iam_service = googleapiclient.discovery.build("iam", "v1", credentials=self.credentials)
        try:
            service_account = (
                iam_service.projects()
                .serviceAccounts()
                .create(
                    name="projects/" + self.project_id,
                    body={
                        "accountId": name,
                        "serviceAccount": {
                            "displayName": name,
                        },
                    },
                )
                .execute()
            )
            return service_account["email"]
        except googleapiclient.errors.HttpError as e:
            if e.status_code == 409:
                return gcp_utils.get_service_account_email(self.project_id, name)
            elif e.status_code == 403:
                raise BackendConfigError(
                    "Not enough permissions. Default credentials must have Service Account Admin role.",
                    code="not_enough_permissions",
                )
            raise e

    def _grant_roles_to_service_account(self, service_account_email: str):
        service = googleapiclient.discovery.build(
            "cloudresourcemanager", "v1", credentials=self.credentials
        )
        try:
            policy = service.projects().getIamPolicy(resource=self.project_id).execute()
            self._add_roles_to_policy(
                policy=policy,
                service_account_email=service_account_email,
                roles=self._get_service_account_roles(),
            )
            service.projects().setIamPolicy(
                resource=self.project_id, body={"policy": policy}
            ).execute()
        except googleapiclient.errors.HttpError as e:
            if e.status_code == 403:
                raise BackendConfigError(
                    "Not enough permissions. Default credentials must have Security Admin role.",
                    code="not_enough_permissions",
                )
            raise e

    def _get_service_account_roles(self) -> List[str]:
        return [
            "roles/compute.admin",
            "roles/logging.admin",
            "roles/secretmanager.admin",
            "roles/storage.admin",
            "roles/iam.serviceAccountUser",
        ]

    def _add_roles_to_policy(self, policy: Dict, service_account_email: str, roles: List[str]):
        member = f"serviceAccount:{service_account_email}"
        for role in roles:
            policy["bindings"].append({"role": role, "members": [member]})

    def _check_if_can_create_service_account_key(self, service_account_email: str):
        try:
            gcp_auth.create_service_account_key(
                iam_service=googleapiclient.discovery.build(
                    "iam", "v1", credentials=self.credentials
                ),
                project_id=self.project_id,
                service_account_email=service_account_email,
            )
        except gcp_auth.NotEnoughPermissionError:
            raise BackendConfigError(
                "Not enough permissions. Default credentials must have Service Account Key Admin role.",
                code="not_enough_permissions",
            )

    def _raise_invalid_credentials_error(self, fields: Optional[List[List[str]]] = None):
        raise BackendConfigError(
            "Invalid credentials",
            code="invalid_credentials",
            fields=fields,
        )
