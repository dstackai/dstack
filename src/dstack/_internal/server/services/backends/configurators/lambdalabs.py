import json
from typing import List

from dstack._internal.core.backends.lambdalabs import LambdaBackend, api_client
from dstack._internal.core.backends.lambdalabs.config import LambdaConfig
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.core.models.backends.lambdalabs import (
    AnyLambdaConfigInfo,
    LambdaConfigInfo,
    LambdaConfigInfoWithCreds,
    LambdaConfigInfoWithCredsPartial,
    LambdaConfigValues,
    LambdaCreds,
    LambdaStoredConfig,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    raise_invalid_credentials_error,
)

REGIONS = [
    "us-south-1",
    "us-west-2",
    "us-west-1",
    "us-midwest-1",
    "us-west-3",
    "us-east-1",
    "australia-southeast-1",
    "europe-central-1",
    "asia-south-1",
    "me-west-1",
    "europe-south-1",
    "asia-northeast-1",
]

DEFAULT_REGION = "us-east-1"


class LambdaConfigurator(Configurator):
    TYPE: BackendType = BackendType.LAMBDA

    def get_config_values(self, config: LambdaConfigInfoWithCredsPartial) -> LambdaConfigValues:
        config_values = LambdaConfigValues()
        if config.creds is None:
            return config_values
        self._validate_lambda_api_key(config.creds.api_key)
        config_values.regions = self._get_regions_element(
            selected=config.regions or [DEFAULT_REGION]
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: LambdaConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=LambdaStoredConfig(
                **LambdaConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=LambdaCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyLambdaConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return LambdaConfigInfoWithCreds.__response__.parse_obj(config)
        return LambdaConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> LambdaBackend:
        config = self._get_backend_config(model)
        return LambdaBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> LambdaConfig:
        return LambdaConfig.__response__(
            **json.loads(model.config),
            creds=LambdaCreds.parse_raw(model.auth),
        )

    def _validate_lambda_api_key(self, api_key: str):
        client = api_client.LambdaAPIClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])

    def _get_regions_element(self, selected: List[str]) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for r in REGIONS:
            element.values.append(ConfigElementValue(value=r, label=r))
        return element
