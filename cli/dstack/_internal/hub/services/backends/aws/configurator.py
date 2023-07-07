import json
from typing import Dict, List, Optional, Tuple, Union

import botocore.exceptions
from boto3.session import Session

from dstack._internal.backend.aws import AwsBackend
from dstack._internal.backend.aws.config import DEFAULT_REGION_NAME, AWSConfig
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.models import (
    AWSBucketProjectElement,
    AWSBucketProjectElementValue,
    AWSProjectConfig,
    AWSProjectConfigWithCreds,
    AWSProjectConfigWithCredsPartial,
    AWSProjectCreds,
    AWSProjectValues,
    ProjectElement,
    ProjectElementValue,
    ProjectMultiElement,
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

    def configure_project(
        self, project_config: AWSProjectConfigWithCredsPartial
    ) -> AWSProjectValues:
        if (
            project_config.region_name is not None
            and project_config.region_name not in REGION_VALUES
        ):
            raise BackendConfigError(f"Invalid AWS region {project_config.region_name}")

        project_values = AWSProjectValues()
        session = Session()
        if session.region_name is None:
            session = Session(region_name=project_config.region_name or DEFAULT_REGION_NAME)

        project_values.default_credentials = self._valid_credentials(session=session)

        if project_config.credentials is None:
            return project_values

        project_credentials = project_config.credentials.__root__
        if project_credentials.type == "access_key":
            session = Session(
                region_name=project_config.region_name,
                aws_access_key_id=project_credentials.access_key,
                aws_secret_access_key=project_credentials.secret_key,
            )
            if not self._valid_credentials(session=session):
                self._raise_invalid_credentials_error(
                    fields=[["credentials", "access_key"], ["credentials", "secret_key"]]
                )
        elif not project_values.default_credentials:
            self._raise_invalid_credentials_error(fields=[["credentials"]])

        # TODO validate config values
        project_values.region_name = self._get_hub_region_element(selected=session.region_name)
        project_values.extra_regions = self._get_hub_extra_regions_element(
            region=session.region_name,
            selected=project_config.extra_regions or [],
        )
        project_values.s3_bucket_name = self._get_hub_buckets_element(
            session=session,
            region=session.region_name,
            selected=project_config.s3_bucket_name,
        )
        project_values.ec2_subnet_id = self._get_hub_subnet_element(
            session=session, selected=project_config.ec2_subnet_id
        )
        return project_values

    def create_project(self, project_config: AWSProjectConfigWithCreds) -> Tuple[Dict, Dict]:
        config_data = {
            "region_name": project_config.region_name,
            "extra_regions": project_config.extra_regions,
            "s3_bucket_name": project_config.s3_bucket_name.replace("s3://", ""),
            "ec2_subnet_id": project_config.ec2_subnet_id,
        }
        auth_data = project_config.credentials.__root__.dict()
        return config_data, auth_data

    def get_project_config(
        self, project: Project, include_creds: bool
    ) -> Union[AWSProjectConfig, AWSProjectConfigWithCreds]:
        json_config = json.loads(project.config)
        region_name = json_config["region_name"]
        s3_bucket_name = json_config["s3_bucket_name"]
        ec2_subnet_id = json_config["ec2_subnet_id"]
        extra_regions = json_config.get("extra_regions", [])
        if include_creds:
            json_auth = json.loads(project.auth)
            return AWSProjectConfigWithCreds(
                region_name=region_name,
                region_name_title=region_name,
                extra_regions=extra_regions,
                s3_bucket_name=s3_bucket_name,
                ec2_subnet_id=ec2_subnet_id,
                credentials=AWSProjectCreds.parse_obj(json_auth),
            )
        return AWSProjectConfig(
            region_name=region_name,
            region_name_title=region_name,
            extra_regions=extra_regions,
            s3_bucket_name=s3_bucket_name,
            ec2_subnet_id=ec2_subnet_id,
        )

    def get_backend(self, project: Project) -> AwsBackend:
        config_data = json.loads(project.config)
        auth_data = json.loads(project.auth)
        config = AWSConfig(
            bucket_name=config_data.get("bucket")
            or config_data.get("bucket_name")
            or config_data.get("s3_bucket_name"),
            region_name=config_data.get("region_name"),
            extra_regions=config_data.get("extra_regions", []),
            subnet_id=config_data.get("subnet_id")
            or config_data.get("ec2_subnet_id")
            or config_data.get("subnet"),
            credentials=auth_data,
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

    def _get_hub_region_element(self, selected: Optional[str]) -> ProjectElement:
        element = ProjectElement(selected=selected)
        for r in REGIONS:
            element.values.append(ProjectElementValue(value=r[1], label=r[1]))
        return element

    def _get_hub_extra_regions_element(
        self, region: str, selected: List[str]
    ) -> ProjectMultiElement:
        element = ProjectMultiElement(selected=selected)
        for r in REGION_VALUES:
            if r != region:
                element.values.append(ProjectElementValue(value=r, label=r))
        return element

    def _get_hub_buckets_element(
        self, session: Session, region: str, selected: Optional[str]
    ) -> AWSBucketProjectElement:
        if selected is not None:
            self._validate_hub_bucket(session=session, region=region, bucket_name=selected)
        element = AWSBucketProjectElement(selected=selected)
        s3_client = session.client("s3")
        response = s3_client.list_buckets()
        for bucket in response["Buckets"]:
            element.values.append(
                AWSBucketProjectElementValue(
                    name=bucket["Name"],
                    created=bucket["CreationDate"].strftime("%d.%m.%Y %H:%M:%S"),
                    region=region,
                )
            )
        return element

    def _validate_hub_bucket(self, session: Session, region: str, bucket_name: str):
        s3_client = session.client("s3")
        try:
            response = s3_client.head_bucket(Bucket=bucket_name)
            bucket_region = response["ResponseMetadata"]["HTTPHeaders"]["x-amz-bucket-region"]
            if bucket_region.lower() != region:
                raise BackendConfigError(
                    "The bucket belongs to another AWS region",
                    code="invalid_bucket",
                    fields=[["s3_bucket_name"]],
                )
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

    def _get_hub_subnet_element(self, session: Session, selected: Optional[str]) -> ProjectElement:
        element = ProjectElement(selected=selected)
        _ec2 = session.client("ec2")
        response = _ec2.describe_subnets()
        for subnet in response["Subnets"]:
            element.values.append(
                ProjectElementValue(
                    value=subnet["SubnetId"],
                    label=subnet["SubnetId"],
                )
            )
        return element
