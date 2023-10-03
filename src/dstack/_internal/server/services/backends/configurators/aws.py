import json
from abc import ABC
from typing import List

import boto3.session
import botocore.exceptions
from boto3.session import Session

from dstack._internal.core.backends.aws import AWSBackend
from dstack._internal.core.backends.aws.config import AWSConfig
from dstack._internal.core.backends.base import Backend
from dstack._internal.core.models.backends.aws import (
    AnyAWSConfigInfo,
    AWSConfigInfo,
    AWSConfigInfoWithCreds,
    AWSConfigInfoWithCredsPartial,
    AWSConfigValues,
    AWSCreds,
    AWSStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import (
    raise_invalid_credentials_error,
)

REGIONS = [
    ("US East, N. Virginia", "us-east-1"),
    ("US East, Ohio", "us-east-2"),
    ("US West, N. California", "us-west-1"),
    ("US West, Oregon", "us-west-2"),
    ("Asia Pacific, Singapore", "ap-southeast-1"),
    ("Canada, Central", "ca-central-1"),
    ("Europe, Frankfurt", "eu-central-1"),
    ("Europe, Ireland", "eu-west-1"),
    ("Europe, London", "eu-west-2"),
    ("Europe, Paris", "eu-west-3"),
    ("Europe, Stockholm", "eu-north-1"),
]
REGION_VALUES = [r[1] for r in REGIONS]
DEFAULT_REGION = "us-east-1"


class AWSConfigurator(ABC):
    TYPE: BackendType = BackendType.AWS

    def get_config_values(self, config: AWSConfigInfoWithCredsPartial) -> AWSConfigValues:
        config_values = AWSConfigValues()
        # TODO support default credentials
        config_values.default_creds = False
        if config.creds is None:
            return config_values

        session = boto3.session.Session(
            region_name=DEFAULT_REGION,
            aws_access_key_id=config.creds.access_key,
            aws_secret_access_key=config.creds.secret_key,
        )
        if not self._valid_credentials(session=session):
            raise_invalid_credentials_error(
                fields=[
                    ["creds", "access_key"],
                    ["creds", "secret_key"],
                ]
            )
        config_values.regions = self._get_regions_element(
            selected=config.regions or [DEFAULT_REGION]
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: AWSConfigInfoWithCreds
    ) -> BackendModel:
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=AWSStoredConfig(**AWSConfigInfo.parse_obj(config).dict()).json(),
            auth=AWSCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyAWSConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return AWSConfigInfoWithCreds.parse_obj(config)
        return AWSConfigInfo.parse_obj(config)

    def get_backend(self, model: BackendModel) -> AWSBackend:
        config = self._get_backend_config(model)
        return AWSBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> AWSConfig:
        return AWSConfig(
            **json.loads(model.config),
            creds=AWSCreds.parse_raw(model.auth).__root__,
        )

    def _valid_credentials(self, session: Session) -> bool:
        sts = session.client("sts")
        try:
            sts.get_caller_identity()
        except (botocore.exceptions.ClientError, botocore.exceptions.NoCredentialsError):
            return False
        return True

    def _get_regions_element(self, selected: List[str]) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for r in REGION_VALUES:
            element.values.append(ConfigElementValue(value=r, label=r))
        return element
