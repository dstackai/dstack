from abc import ABC
from typing import List

import boto3.session
import botocore.exceptions
from boto3.session import Session

from dstack._internal.core.backends.aws import AwsBackend
from dstack._internal.core.backends.aws.config import AWSConfig
from dstack._internal.core.backends.base import Backend
from dstack._internal.core.models.backends import (
    AnyConfigInfo,
    AWSConfigInfo,
    AWSConfigInfoWithCreds,
    AWSConfigInfoWithCredsPartial,
    AWSConfigValues,
    AWSCreds,
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.base import raise_invalid_credentials_error

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
    NAME: BackendType = BackendType.AWS

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
            type=self.NAME,
            config=AWSConfigInfo.parse_obj(config).json(),
            auth=AWSCreds.parse_obj(config.creds).__root__.json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyConfigInfo:
        config = AWSConfigInfo.parse_raw(model.config)
        creds = AWSCreds.parse_raw(model.auth).__root__
        if include_creds:
            return AWSConfigInfoWithCreds(
                regions=config.regions,
                creds=creds,
            )
        return config

    def get_backend(self, model: BackendModel) -> Backend:
        config_info = self.get_config_info(model=model, include_creds=True)
        config = AWSConfig(regions=config_info.regions, creds=config_info.creds)
        return AwsBackend(config=config)

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
