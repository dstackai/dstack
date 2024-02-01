import json
from typing import Dict, List

import googleapiclient.discovery
import googleapiclient.errors
from google.auth.credentials import Credentials

from dstack._internal.core.backends.gcp import GCPBackend, auth
from dstack._internal.core.backends.gcp import utils as gcp_utils
from dstack._internal.core.backends.gcp.config import GCPConfig
from dstack._internal.core.errors import BackendAuthError, ServerClientError
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElement,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.core.models.backends.gcp import (
    AnyGCPConfigInfo,
    GCPConfigInfo,
    GCPConfigInfoWithCreds,
    GCPConfigInfoWithCredsPartial,
    GCPConfigValues,
    GCPCreds,
    GCPDefaultCreds,
    GCPServiceAccountCreds,
    GCPStoredConfig,
)
from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    raise_invalid_credentials_error,
)

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
REGIONS = [r for loc in LOCATIONS for r in loc["regions"]]
DEFAULT_REGIONS = REGIONS
MAIN_REGION = "us-east1"


class GCPConfigurator(Configurator):
    TYPE: BackendType = BackendType.GCP

    def get_default_configs(self) -> List[GCPConfigInfoWithCreds]:
        if not auth.default_creds_available():
            return []
        try:
            _, project_id = auth.authenticate(GCPDefaultCreds())
        except BackendAuthError:
            return []

        if project_id is None:
            return []

        return [
            GCPConfigInfoWithCreds(
                project_id=project_id,
                regions=DEFAULT_REGIONS,
                creds=GCPDefaultCreds(),
            )
        ]

    def get_config_values(self, config: GCPConfigInfoWithCredsPartial) -> GCPConfigValues:
        config_values = GCPConfigValues(project_id=None, regions=None)
        config_values.default_creds = (
            settings.DEFAULT_CREDS_ENABLED and auth.default_creds_available()
        )
        if config.creds is None:
            return config_values
        if isinstance(config.creds, GCPDefaultCreds) and not settings.DEFAULT_CREDS_ENABLED:
            raise_invalid_credentials_error(fields=[["creds"]])
        try:
            _, project_id = auth.authenticate(creds=config.creds)
        except BackendAuthError:
            if isinstance(config.creds, GCPServiceAccountCreds):
                raise_invalid_credentials_error(fields=[["creds", "data"]])
            else:
                raise_invalid_credentials_error(fields=[["creds"]])
        if (
            project_id is not None
            and config.project_id is not None
            and config.project_id != project_id
        ):
            raise ServerClientError(msg="Wrong project_id", fields=[["project_id"]])
        config_values.project_id = self._get_project_id_element(selected=project_id)
        if config.project_id is None:
            return config_values
        config_values.regions = self._get_regions_element(
            selected=config.regions or DEFAULT_REGIONS
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: GCPConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = DEFAULT_REGIONS
        credentials, _ = auth.authenticate(creds=config.creds)
        service_account_email = getattr(credentials, "service_account_email", None)
        if service_account_email is None:
            service_account_email = self._get_or_create_service_account(
                credentials=credentials,
                project_id=config.project_id,
                name=gcp_utils.get_service_account_name(project.name),
            )
            self._grant_roles_to_service_account(
                credentials=credentials,
                project_id=config.project_id,
                service_account_email=service_account_email,
            )
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=GCPStoredConfig(
                **GCPConfigInfo.parse_obj(config).dict(),
                service_account_email=service_account_email,
            ).json(),
            auth=GCPCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyGCPConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return GCPConfigInfoWithCreds.parse_obj(config)
        return GCPConfigInfo.parse_obj(config)

    def get_backend(self, model: BackendModel) -> GCPBackend:
        config = self._get_backend_config(model)
        return GCPBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> GCPConfig:
        return GCPConfig(
            **json.loads(model.config),
            creds=GCPCreds.parse_raw(model.auth).__root__,
        )

    def _get_project_id_element(
        self,
        selected: str,
    ) -> ConfigElement:
        element = ConfigElement(selected=selected)
        element.values.append(ConfigElementValue(value=selected, label=selected))
        return element

    def _get_regions_element(
        self,
        selected: List[str],
    ) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for region_name in REGIONS:
            element.values.append(ConfigElementValue(value=region_name, label=region_name))
        return element

    def _get_or_create_service_account(
        self, credentials: Credentials, project_id: str, name: str
    ) -> str:
        iam_service = googleapiclient.discovery.build("iam", "v1", credentials=credentials)
        try:
            service_account = (
                iam_service.projects()
                .serviceAccounts()
                .create(
                    name="projects/" + project_id,
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
                return gcp_utils.get_service_account_email(project_id, name)
            elif e.status_code == 403:
                raise ServerClientError(
                    "Not enough permissions. Default credentials must have Service Account Admin role.",
                )
            raise e

    def _grant_roles_to_service_account(
        self, credentials: Credentials, project_id: str, service_account_email: str
    ):
        service = googleapiclient.discovery.build(
            "cloudresourcemanager", "v1", credentials=credentials
        )
        try:
            policy = service.projects().getIamPolicy(resource=project_id).execute()
            self._add_roles_to_policy(
                policy=policy,
                service_account_email=service_account_email,
                roles=self._get_service_account_roles(),
            )
            service.projects().setIamPolicy(resource=project_id, body={"policy": policy}).execute()
        except googleapiclient.errors.HttpError as e:
            if e.status_code == 403:
                raise ServerClientError(
                    "Not enough permissions. Default credentials must have Security Admin role.",
                )
            raise e

    def _get_service_account_roles(self) -> List[str]:
        return [
            "roles/compute.admin",
            "roles/iam.serviceAccountUser",
        ]

    def _add_roles_to_policy(self, policy: Dict, service_account_email: str, roles: List[str]):
        member = f"serviceAccount:{service_account_email}"
        for role in roles:
            policy["bindings"].append({"role": role, "members": [member]})
