import json
from typing import Dict, List, Optional, Tuple, Union

import botocore
import botocore.exceptions
from boto3.session import Session
from requests import HTTPError

from dstack._internal.backend.lambdalabs import LambdaBackend
from dstack._internal.backend.lambdalabs.api_client import LambdaAPIClient
from dstack._internal.backend.lambdalabs.config import (
    AWSStorageConfig,
    AWSStorageConfigCredentials,
    LambdaConfig,
)
from dstack._internal.hub.db.models import Backend as DBBackend
from dstack._internal.hub.schemas import (
    AWSBackendAccessKeyCreds,
    AWSStorageBackendConfig,
    AWSStorageBackendConfigWithCreds,
    AWSStorageBackendConfigWithCredsPartial,
    AWSStorageBackendValues,
    BackendElement,
    BackendElementValue,
    BackendMultiElement,
    LambdaBackendConfig,
    LambdaBackendConfigWithCreds,
    LambdaBackendConfigWithCredsPartial,
    LambdaBackendValues,
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

    def configure_backend(
        self, backend_config: LambdaBackendConfigWithCredsPartial
    ) -> LambdaBackendValues:
        selected_storage_backend = None
        if backend_config.storage_backend is not None:
            selected_storage_backend = backend_config.storage_backend.type
        storage_backend_type = self._get_storage_backend_type_element(
            selected=selected_storage_backend
        )
        backend_values = LambdaBackendValues(storage_backend_type=storage_backend_type)
        if backend_config.api_key is None:
            return backend_values
        self._validate_lambda_api_key(api_key=backend_config.api_key)
        backend_values.regions = self._get_regions_element(selected=backend_config.regions)
        if (
            backend_config.storage_backend is None
            or backend_config.storage_backend.credentials is None
        ):
            return backend_values
        backend_values.storage_backend_values = self._get_aws_storage_backend_values(
            backend_config.storage_backend
        )
        return backend_values

    def create_backend(
        self, project_name: str, backend_config: LambdaBackendConfigWithCreds
    ) -> Tuple[Dict, Dict]:
        config_data = {
            "regions": backend_config.regions,
            "storage_backend": self._get_aws_storage_backend_config_data(
                backend_config.storage_backend
            ),
        }
        auth_data = {
            "api_key": backend_config.api_key,
            "storage_backend": {"credentials": backend_config.storage_backend.credentials.dict()},
        }
        return config_data, auth_data

    def get_backend_config(
        self, db_backend: DBBackend, include_creds: bool
    ) -> Union[LambdaBackendConfig, LambdaBackendConfigWithCreds]:
        config_data = json.loads(db_backend.config)
        if include_creds:
            auth_data = json.loads(db_backend.auth)
            return LambdaBackendConfigWithCreds(
                regions=config_data["regions"],
                api_key=auth_data["api_key"],
                storage_backend=AWSStorageBackendConfigWithCreds(
                    bucket_name=config_data["storage_backend"]["bucket"],
                    credentials=AWSBackendAccessKeyCreds.parse_obj(
                        auth_data["storage_backend"]["credentials"]
                    ),
                ),
            )
        return LambdaBackendConfig(
            regions=config_data["regions"],
            storage_backend=AWSStorageBackendConfig(
                bucket_name=config_data["storage_backend"]["bucket"]
            ),
        )

    def get_backend(self, db_backend: DBBackend) -> LambdaBackend:
        config_data = json.loads(db_backend.config)
        auth_data = json.loads(db_backend.auth)
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

    def _get_storage_backend_type_element(self, selected: Optional[str]) -> BackendElement:
        element = BackendElement(
            values=[BackendElementValue(value="aws", label="AWS S3")], selected="aws"
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

    def _get_regions_element(self, selected: Optional[List[str]]) -> BackendMultiElement:
        if selected is not None:
            for r in selected:
                if r not in REGIONS:
                    raise BackendConfigError(
                        "Invalid regions",
                        code="invalid_regions",
                        fields=[["regions"]],
                    )
        element = BackendMultiElement(
            selected=selected or REGIONS,
            values=[BackendElementValue(value=r, label=r) for r in REGIONS],
        )
        return element

    def _get_aws_storage_backend_values(
        self, config: AWSStorageBackendConfigWithCredsPartial
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
    ) -> BackendElement:
        element = BackendElement(selected=selected)
        s3_client = session.client("s3")
        try:
            response = s3_client.list_buckets()
        except botocore.exceptions.ClientError:
            # We'll suggest no buckets if the user has no permission to list them
            return element
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
                BackendElementValue(
                    value=bucket_name,
                    label=bucket_name,
                )
            )
        return element

    def _get_aws_storage_backend_config_data(
        self, config: AWSStorageBackendConfigWithCreds
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
        try:
            response = s3_client.head_bucket(Bucket=bucket)
        except botocore.exceptions.ClientError:
            raise BackendConfigError(
                "Permissions for getting bucket region are required",
                code="permissions_error",
                fields=[
                    ["storage_backend", "credentials", "access_key"],
                    ["storage_backend", "credentials", "secret_key"],
                ],
            )
        region = response["ResponseMetadata"]["HTTPHeaders"]["x-amz-bucket-region"]
        return region
