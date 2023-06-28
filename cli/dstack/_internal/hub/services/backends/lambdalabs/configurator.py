import json
from typing import Dict, Optional, Tuple, Union

import botocore
from boto3.session import Session
from requests import HTTPError

from dstack._internal.backend.lambdalabs import LambdaBackend
from dstack._internal.backend.lambdalabs.api_client import LambdaAPIClient
from dstack._internal.backend.lambdalabs.config import (
    AWSStorageConfig,
    AWSStorageConfigCredentials,
    LambdaConfig,
)
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.models import (
    AWSProjectAccessKeyCreds,
    AWSStorageBackendValues,
    AWSStorageProjectConfig,
    AWSStorageProjectConfigWithCreds,
    AWSStorageProjectConfigWithCredsPartial,
    LambdaProjectConfig,
    LambdaProjectConfigWithCreds,
    LambdaProjectConfigWithCredsPartial,
    LambdaProjectValues,
    ProjectElement,
    ProjectElementValue,
    ProjectValues,
)
from dstack._internal.hub.services.backends.base import BackendConfigError


class LambdaConfigurator:
    NAME = "lambda"

    def get_backend_class(self) -> type:
        return LambdaBackend

    def configure_project(self, config: LambdaProjectConfigWithCredsPartial) -> ProjectValues:
        selected_storage_backend = None
        if config.storage_backend is not None:
            selected_storage_backend = config.storage_backend.type
        storage_backend_type = self._get_storage_backend_type_element(
            selected=selected_storage_backend
        )
        project_values = LambdaProjectValues(storage_backend_type=storage_backend_type)
        if config.api_key is None:
            return project_values
        self._validate_lambda_api_key(api_key=config.api_key)
        if config.storage_backend is None or config.storage_backend.credentials is None:
            return project_values
        project_values.storage_backend_values = self._get_aws_storage_backend_values(
            config.storage_backend
        )
        return project_values

    def create_config_auth_data_from_project_config(
        self, project_config: LambdaProjectConfigWithCreds
    ) -> Tuple[Dict, Dict]:
        config_data = {
            "backend": "lambda",
            "storage_backend": self._get_aws_storage_backend_config_data(
                project_config.storage_backend
            ),
        }
        auth_data = {
            "api_key": project_config.api_key,
            "storage_backend": {"credentials": project_config.storage_backend.credentials.dict()},
        }
        return config_data, auth_data

    def get_project_config_from_project(
        self, project: Project, include_creds: bool
    ) -> Union[LambdaProjectConfig, LambdaProjectConfigWithCreds]:
        config_data = json.loads(project.config)
        if include_creds:
            auth_data = json.loads(project.auth)
            return LambdaProjectConfigWithCreds(
                api_key=auth_data["api_key"],
                storage_backend=AWSStorageProjectConfigWithCreds(
                    bucket_name=config_data["storage_backend"]["bucket"],
                    credentials=AWSProjectAccessKeyCreds.parse_obj(
                        auth_data["storage_backend"]["credentials"]
                    ),
                ),
            )
        return LambdaProjectConfig(
            storage_backend=AWSStorageProjectConfig(
                bucket_name=config_data["storage_backend"]["bucket"]
            )
        )

    def get_backend_config_from_hub_config_data(
        self, project_name: str, config_data: Dict, auth_data: Dict
    ) -> LambdaConfig:
        return LambdaConfig(
            api_key=auth_data["api_key"],
            storage_config=AWSStorageConfig(
                bucket=config_data["storage_backend"]["bucket"],
                region=config_data["storage_backend"]["region"],
                credentials=AWSStorageConfigCredentials(
                    access_key=auth_data["storage_backend"]["credentials"]["access_key"],
                    secret_key=auth_data["storage_backend"]["credentials"]["secret_key"],
                ),
            ),
        )

    def _get_storage_backend_type_element(self, selected: Optional[str]) -> ProjectElement:
        element = ProjectElement(
            values=[ProjectElementValue(value="aws", label="AWS")], selected="aws"
        )
        return element

    def _validate_lambda_api_key(self, api_key: str):
        client = LambdaAPIClient(api_key=api_key)
        try:
            client.list_instance_types()
        except HTTPError as e:
            if e.response.status_code in [401, 403]:
                raise BackendConfigError(
                    "Invalid credentials",
                    code="invalid_credentials",
                    fields=[["api_key"]],
                )
            raise e

    def _get_aws_storage_backend_values(
        self, config: AWSStorageProjectConfigWithCredsPartial
    ) -> AWSStorageBackendValues:
        session = Session(
            aws_access_key_id=config.credentials.access_key,
            aws_secret_access_key=config.credentials.secret_key,
        )
        self._validate_aws_credentials(session=session)
        storage_backend_values = AWSStorageBackendValues()
        storage_backend_values.bucket_name = self._get_aws_bucket_element(
            session=session, selected=config.bucket_name
        )
        return storage_backend_values

    def _validate_aws_credentials(self, session: Session):
        sts = session.client("sts")
        try:
            sts.get_caller_identity()
        except botocore.exceptions.ClientError:
            raise BackendConfigError(
                "Invalid credentials",
                code="invalid_credentials",
                fields=[
                    ["storage_backend", "credentials", "access_key"],
                    ["storage_backend", "credentials", "secret_key"],
                ],
            )

    def _get_aws_bucket_element(
        self, session: Session, selected: Optional[str] = None
    ) -> ProjectElement:
        element = ProjectElement(selected=selected)
        s3_client = session.client("s3")
        response = s3_client.list_buckets()
        for bucket in response["Buckets"]:
            element.values.append(
                ProjectElementValue(
                    value=bucket["Name"],
                    label=bucket["Name"],
                )
            )
        return element

    def _get_aws_storage_backend_config_data(
        self, config: AWSStorageProjectConfigWithCreds
    ) -> Dict:
        session = Session(
            aws_access_key_id=config.credentials.access_key,
            aws_secret_access_key=config.credentials.secret_key,
        )
        return {
            "backend": "aws",
            "bucket": config.bucket_name,
            "region": self._get_aws_bucket_region(session, config.bucket_name),
        }

    def _get_aws_bucket_region(self, session: Session, bucket: str) -> str:
        s3_client = session.client("s3")
        response = s3_client.head_bucket(Bucket=bucket)
        region = response["ResponseMetadata"]["HTTPHeaders"]["x-amz-bucket-region"]
        return region
