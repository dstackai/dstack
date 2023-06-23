import os
from typing import Dict, Tuple, Union

from dstack._internal.backend.lambdalabs import LambdaBackend
from dstack._internal.backend.lambdalabs.config import (
    AWSStorageConfig,
    AWSStorageConfigCredentials,
    LambdaConfig,
)
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.models import (
    LambdaProjectConfig,
    LambdaProjectConfigWithCreds,
    ProjectValues,
)


class LambdaConfigurator:
    NAME = "lambda"

    def get_backend_class(self) -> type:
        return LambdaBackend

    def configure_project(self, config_data: Dict) -> ProjectValues:
        return None

    def create_config_auth_data_from_project_config(
        self, project_config: LambdaProjectConfigWithCreds
    ) -> Tuple[Dict, Dict]:
        config_data = LambdaProjectConfig.parse_obj(project_config).dict()
        auth_data = {"api_key": project_config.api_key}
        return config_data, auth_data

    def get_project_config_from_project(
        self, project: Project, include_creds: bool
    ) -> Union[LambdaProjectConfig, LambdaProjectConfigWithCreds]:
        return LambdaProjectConfig()

    def get_backend_config_from_hub_config_data(
        self, project_name: str, config_data: Dict, auth_data: Dict
    ) -> LambdaConfig:
        return LambdaConfig(
            api_key=os.environ["LAMBDA_API_KEY"],
            storage_config=AWSStorageConfig(
                region="eu-west-1",
                bucket="dstack-lambda-eu-west-1",
                credentials=AWSStorageConfigCredentials(
                    access_key=os.environ["AWS_ACCESS_KEY_ID"],
                    secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
                ),
            ),
        )
