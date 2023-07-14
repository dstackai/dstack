import json
from typing import Dict, List, Optional, Tuple, Union

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
    ProjectMultiElement,
)
from dstack._internal.hub.services.backends.base import BackendConfigError, Configurator

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


class LambdaConfigurator(Configurator):
    NAME = "lambda"

    def configure_project(
        self, project_config: LambdaProjectConfigWithCredsPartial
    ) -> LambdaProjectValues:
        selected_storage_backend = None
        if project_config.storage_backend is not None:
            selected_storage_backend = project_config.storage_backend.type
        storage_backend_type = self._get_storage_backend_type_element(
            selected=selected_storage_backend
        )
        project_values = LambdaProjectValues(storage_backend_type=storage_backend_type)
        if project_config.api_key is None:
            return project_values
        self._validate_lambda_api_key(api_key=project_config.api_key)
        project_values.regions = self._get_regions_element(selected=project_config.regions)
        if (
            project_config.storage_backend is None
            or project_config.storage_backend.credentials is None
        ):
            return project_values
        project_values.storage_backend_values = self._get_aws_storage_backend_values(
            project_config.storage_backend
        )
        return project_values

    def create_project(self, project_config: LambdaProjectConfigWithCreds) -> Tuple[Dict, Dict]:
        config_data = {
            "regions": project_config.regions,
            "storage_backend": self._get_aws_storage_backend_config_data(
                project_config.storage_backend
            ),
        }
        auth_data = {
            "api_key": project_config.api_key,
            "storage_backend": {"credentials": project_config.storage_backend.credentials.dict()},
        }
        return config_data, auth_data

    def get_project_config(
        self, project: Project, include_creds: bool
    ) -> Union[LambdaProjectConfig, LambdaProjectConfigWithCreds]:
        config_data = json.loads(project.config)
        if include_creds:
            auth_data = json.loads(project.auth)
            return LambdaProjectConfigWithCreds(
                regions=config_data["regions"],
                api_key=auth_data["api_key"],
                storage_backend=AWSStorageProjectConfigWithCreds(
                    bucket_name=config_data["storage_backend"]["bucket"],
                    credentials=AWSProjectAccessKeyCreds.parse_obj(
                        auth_data["storage_backend"]["credentials"]
                    ),
                ),
            )
        return LambdaProjectConfig(
            regions=config_data["regions"],
            storage_backend=AWSStorageProjectConfig(
                bucket_name=config_data["storage_backend"]["bucket"]
            ),
        )

    def get_backend(self, project: Project) -> LambdaBackend:
        config_data = json.loads(project.config)
        auth_data = json.loads(project.auth)
        config = LambdaConfig(
            regions=config_data["regions"],
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
        return LambdaBackend(config)

    def _get_storage_backend_type_element(self, selected: Optional[str]) -> ProjectElement:
        element = ProjectElement(
            values=[ProjectElementValue(value="aws", label="AWS S3")], selected="aws"
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

    def _get_regions_element(self, selected: Optional[List[str]]) -> ProjectMultiElement:
        if selected is not None:
            for r in selected:
                if r not in REGIONS:
                    raise BackendConfigError(
                        "Invalid regions",
                        code="invalid_regions",
                        fields=[["regions"]],
                    )
        element = ProjectMultiElement(
            selected=selected or REGIONS,
            values=[ProjectElementValue(value=r, label=r) for r in REGIONS],
        )
        return element

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
        bucket_names = []
        for bucket in response["Buckets"]:
            bucket_names.append(bucket["Name"])
        if selected is not None and selected not in bucket_names:
            raise BackendConfigError(
                f"The bucket {selected} does not exist",
                code="invalid_bucket",
                fields=[["storage_backend", "bucket_name"]],
            )
        for bucket_name in bucket_names:
            element.values.append(
                ProjectElementValue(
                    value=bucket_name,
                    label=bucket_name,
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
            "type": "aws",
            "bucket": config.bucket_name,
            "region": self._get_aws_bucket_region(session, config.bucket_name),
        }

    def _get_aws_bucket_region(self, session: Session, bucket: str) -> str:
        s3_client = session.client("s3")
        response = s3_client.head_bucket(Bucket=bucket)
        region = response["ResponseMetadata"]["HTTPHeaders"]["x-amz-bucket-region"]
        return region
