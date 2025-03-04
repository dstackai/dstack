import json

import google.cloud.compute_v1 as compute_v1

from dstack._internal.core.backends.gcp import GCPBackend, auth, resources
from dstack._internal.core.backends.gcp.config import GCPConfig
from dstack._internal.core.errors import BackendAuthError, BackendError, ServerClientError
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.core.models.backends.gcp import (
    AnyGCPConfigInfo,
    GCPConfigInfo,
    GCPConfigInfoWithCreds,
    GCPCreds,
    GCPDefaultCreds,
    GCPServiceAccountCreds,
    GCPStoredConfig,
)
from dstack._internal.core.models.common import is_core_model_instance
from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel, DecryptedString, ProjectModel
from dstack._internal.server.services.backends.configurators.base import (
    TAGS_MAX_NUM,
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

    def validate_config(self, config: GCPConfigInfoWithCreds):
        if (
            is_core_model_instance(config.creds, GCPDefaultCreds)
            and not settings.DEFAULT_CREDS_ENABLED
        ):
            raise_invalid_credentials_error(fields=[["creds"]])
        try:
            credentials, _ = auth.authenticate(creds=config.creds, project_id=config.project_id)
        except BackendAuthError as e:
            details = None
            if len(e.args) > 0:
                details = e.args[0]
            if is_core_model_instance(config.creds, GCPServiceAccountCreds):
                raise_invalid_credentials_error(fields=[["creds", "data"]], details=details)
            else:
                raise_invalid_credentials_error(fields=[["creds"]], details=details)
        subnetworks_client = compute_v1.SubnetworksClient(credentials=credentials)
        routers_client = compute_v1.RoutersClient(credentials=credentials)
        self._check_config_tags(config)
        self._check_config_vpc(
            subnetworks_client=subnetworks_client,
            routers_client=routers_client,
            config=config,
        )

    def create_backend(
        self, project: ProjectModel, config: GCPConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = DEFAULT_REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=GCPStoredConfig(
                **GCPConfigInfo.__response__.parse_obj(config).dict(),
            ).json(),
            auth=DecryptedString(plaintext=GCPCreds.parse_obj(config.creds).json()),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyGCPConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return GCPConfigInfoWithCreds.__response__.parse_obj(config)
        return GCPConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> GCPBackend:
        config = self._get_backend_config(model)
        return GCPBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> GCPConfig:
        return GCPConfig.__response__(
            **json.loads(model.config),
            creds=GCPCreds.parse_raw(model.auth.get_plaintext_or_error()).__root__,
        )

    def _check_config_tags(self, config: GCPConfigInfoWithCreds):
        if not config.tags:
            return
        if len(config.tags) > TAGS_MAX_NUM:
            raise ServerClientError(
                f"Maximum number of tags exceeded. Up to {TAGS_MAX_NUM} tags is allowed."
            )
        try:
            resources.validate_labels(config.tags)
        except BackendError as e:
            raise ServerClientError(e.args[0])

    def _check_config_vpc(
        self,
        config: GCPConfigInfoWithCreds,
        subnetworks_client: compute_v1.SubnetworksClient,
        routers_client: compute_v1.RoutersClient,
    ):
        allocate_public_ip = config.public_ips if config.public_ips is not None else True
        nat_check = config.nat_check if config.nat_check is not None else True
        try:
            resources.check_vpc(
                subnetworks_client=subnetworks_client,
                routers_client=routers_client,
                project_id=config.project_id,
                regions=config.regions or DEFAULT_REGIONS,
                vpc_name=config.vpc_name,
                shared_vpc_project_id=config.vpc_project_id,
                allocate_public_ip=allocate_public_ip,
                nat_check=nat_check,
            )
        except BackendError as e:
            raise ServerClientError(e.args[0])
