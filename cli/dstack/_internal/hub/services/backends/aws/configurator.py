import json
from typing import Dict, List, Optional, Tuple, Union

import botocore.exceptions
from boto3.session import Session

from dstack._internal.backend.aws import AwsBackend
from dstack._internal.backend.aws.config import DEFAULT_REGION, AWSConfig
from dstack._internal.hub.db.models import Backend as DBBackend
from dstack._internal.hub.schemas import (
    AWSBackendConfig,
    AWSBackendConfigWithCreds,
    AWSBackendConfigWithCredsPartial,
    AWSBackendCreds,
    AWSBackendValues,
    AWSBucketBackendElement,
    AWSBucketBackendElementValue,
    BackendElement,
    BackendElementValue,
    BackendMultiElement,
)
from dstack._internal.hub.services.backends.base import BackendConfigError, Configurator

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


class AWSConfigurator(Configurator):
    NAME = "aws"

    def configure_backend(
        self, backend_config: AWSBackendConfigWithCredsPartial
    ) -> AWSBackendValues:
        backend_values = AWSBackendValues()
        session = Session()
        if session.region_name is None:
            session = Session(region_name=DEFAULT_REGION)

        backend_values.default_credentials = self._valid_credentials(session=session)

        if backend_config.credentials is None:
            return backend_values

        project_credentials = backend_config.credentials.__root__
        if project_credentials.type == "access_key":
            session = Session(
                region_name=DEFAULT_REGION,
                aws_access_key_id=project_credentials.access_key,
                aws_secret_access_key=project_credentials.secret_key,
            )
            if not self._valid_credentials(session=session):
                self._raise_invalid_credentials_error(
                    fields=[["credentials", "access_key"], ["credentials", "secret_key"]]
                )
        elif not backend_values.default_credentials:
            self._raise_invalid_credentials_error(fields=[["credentials"]])

        backend_values.regions = self._get_hub_regions_element(
            selected=backend_config.regions or [DEFAULT_REGION]
        )
        backend_values.s3_bucket_name = self._get_hub_buckets_element(
            session=session,
            selected=backend_config.s3_bucket_name,
        )
        backend_values.ec2_subnet_id = self._get_hub_subnet_element(
            session=session, selected=backend_config.ec2_subnet_id
        )
        return backend_values

    def create_backend(
        self, project_name: str, backend_config: AWSBackendConfigWithCreds
    ) -> Tuple[Dict, Dict]:
        config_data = {
            "regions": backend_config.regions,
            "s3_bucket_name": backend_config.s3_bucket_name.replace("s3://", ""),
            "ec2_subnet_id": backend_config.ec2_subnet_id,
        }
        auth_data = backend_config.credentials.__root__.dict()
        return config_data, auth_data

    def get_backend_config(
        self, db_backend: DBBackend, include_creds: bool
    ) -> Union[AWSBackendConfig, AWSBackendConfigWithCreds]:
        json_config = json.loads(db_backend.config)
        s3_bucket_name = json_config["s3_bucket_name"]
        regions = json_config.get("regions")
        if regions is None:
            # old regions format
            regions = json_config.get("extra_regions", []) + [json_config.get("region_name")]
        ec2_subnet_id = json_config["ec2_subnet_id"]
        if include_creds:
            json_auth = json.loads(db_backend.auth)
            return AWSBackendConfigWithCreds(
                regions=regions,
                s3_bucket_name=s3_bucket_name,
                ec2_subnet_id=ec2_subnet_id,
                credentials=AWSBackendCreds.parse_obj(json_auth),
            )
        return AWSBackendConfig(
            regions=regions,
            s3_bucket_name=s3_bucket_name,
            ec2_subnet_id=ec2_subnet_id,
        )

    def get_backend(self, db_backend: DBBackend) -> AwsBackend:
        json_config = json.loads(db_backend.config)
        json_auth = json.loads(db_backend.auth)
        regions = json_config.get("regions")
        if regions is None:
            # old regions format
            regions = json_config.get("extra_regions", []) + [json_config.get("region_name")]
        config = AWSConfig(
            bucket_name=json_config.get("s3_bucket_name"),
            regions=regions,
            subnet_id=json_config.get("ec2_subnet_id"),
            credentials=json_auth,
        )
        return AwsBackend(config)

    def _valid_credentials(self, session: Session) -> bool:
        sts = session.client("sts")
        try:
            sts.get_caller_identity()
        except (botocore.exceptions.ClientError, botocore.exceptions.NoCredentialsError):
            return False
        return True

    def _raise_invalid_credentials_error(self, fields: Optional[List[List[str]]] = None):
        raise BackendConfigError(
            "Invalid credentials",
            code="invalid_credentials",
            fields=fields,
        )

    def _get_hub_regions_element(self, selected: List[str]) -> BackendMultiElement:
        for r in selected:
            if r not in REGION_VALUES:
                raise BackendConfigError(
                    f"The region {r} is invalid",
                    code="invalid_region",
                    fields=[["regions"]],
                )
        element = BackendMultiElement(selected=selected)
        for r in REGION_VALUES:
            element.values.append(BackendElementValue(value=r, label=r))
        return element

    def _get_hub_buckets_element(
        self, session: Session, selected: Optional[str]
    ) -> AWSBucketBackendElement:
        if selected:
            self._validate_hub_bucket(session=session, bucket_name=selected)
        element = AWSBucketBackendElement(selected=selected)
        s3_client = session.client("s3")
        try:
            response = s3_client.list_buckets()
        except botocore.exceptions.ClientError:
            # We'll suggest no buckets if the user has no permission to list them
            return element
        for bucket in response["Buckets"]:
            element.values.append(
                AWSBucketBackendElementValue(
                    name=bucket["Name"],
                    created=bucket["CreationDate"].strftime("%d.%m.%Y %H:%M:%S"),
                    region="",
                )
            )
        return element

    def _validate_hub_bucket(self, session: Session, bucket_name: str):
        s3_client = session.client("s3")
        try:
            s3_client.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError as e:
            if (
                hasattr(e, "response")
                and e.response.get("Error")
                and e.response["Error"].get("Code") in ["404", "403"]
            ):
                raise BackendConfigError(
                    f"The bucket {bucket_name} does not exist",
                    code="invalid_bucket",
                    fields=[["s3_bucket_name"]],
                )
            raise e

    def _get_hub_subnet_element(self, session: Session, selected: Optional[str]) -> BackendElement:
        element = BackendElement(selected=selected)
        _ec2 = session.client("ec2")
        response = _ec2.describe_subnets()
        for subnet in response["Subnets"]:
            element.values.append(
                BackendElementValue(
                    value=subnet["SubnetId"],
                    label=subnet["SubnetId"],
                )
            )
        return element
