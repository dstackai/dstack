from typing import List

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.gcp import GCPBackend, auth
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
)
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
REGIONS = [r for l in LOCATIONS for r in l["regions"]]
DEFAULT_REGION = "us-east1"


class GCPConfigurator(Configurator):
    TYPE: BackendType = BackendType.GCP

    def get_config_values(self, config: GCPConfigInfoWithCredsPartial) -> GCPConfigValues:
        config_values = GCPConfigValues()
        # TODO support default credentials
        config_values.default_creds = False
        if config.creds is None:
            return config_values
        try:
            credentials, project_id = auth.authenticate(creds=config.creds)
        except BackendAuthError:
            raise_invalid_credentials_error(
                fields=[
                    ["creds", "data"],
                ]
            )
        if config.project_id is None:
            return config_values
        if config.project_id != project_id:
            raise ServerClientError(msg="Wrong project_id", fields=[["project_id"]])
        config_values.project_id = self._get_project_id_element(selected=project_id)
        config_values.regions = self._get_regions_element(
            selected=config.regions or [DEFAULT_REGION]
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: GCPConfigInfoWithCreds
    ) -> BackendModel:
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=GCPConfigInfo.parse_obj(config).json(),
            auth=GCPCreds.parse_obj(config.creds).__root__.json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyGCPConfigInfo:
        config = GCPConfigInfo.parse_raw(model.config)
        creds = GCPCreds.parse_raw(model.auth).__root__
        if include_creds:
            return GCPConfigInfoWithCreds(
                **config.dict(),
                creds=creds,
            )
        return config

    def get_backend(self, model: BackendModel) -> GCPBackend:
        config_info = self.get_config_info(model=model, include_creds=True)
        config = GCPConfig.parse_obj(config_info)
        return GCPBackend(config=config)

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
