import json
import os
import re
from argparse import Namespace
from pathlib import Path
from typing import Dict, Optional

import boto3
import botocore.exceptions
import yaml
from boto3.session import Session
from botocore.client import BaseClient
from rich import print
from rich.prompt import Confirm, Prompt
from rich_argparse import RichHelpFormatter

from dstack.cli.common import ask_choice, is_termios_available
from dstack.core.config import BackendConfig, Configurator, get_config_path
from dstack.core.error import ConfigError, HubConfigError
from dstack.hub.models import (
    AWSBucketProjectElement,
    AWSBucketProjectElementValue,
    AWSProjectValues,
    ProjectElement,
    ProjectElementValue,
)

regions = [
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

_DEFAULT_REGION_NAME = "us-east-1"

cache = {}


class AWSConfig(BackendConfig):
    bucket_name = None
    region_name = None
    profile_name = None
    subnet_id = None
    credentials = None

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region_name: Optional[str] = None,
        profile_name: Optional[str] = None,
        subnet_id: Optional[str] = None,
        credentials: Optional[Dict] = None,
    ):
        self.bucket_name = bucket_name or os.getenv("DSTACK_AWS_S3_BUCKET")
        self.region_name = (
            region_name
            or os.getenv("DSTACK_AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or _DEFAULT_REGION_NAME
        )
        self.profile_name = (
            profile_name or os.getenv("DSTACK_AWS_PROFILE") or os.getenv("AWS_PROFILE")
        )
        self.subnet_id = subnet_id or os.getenv("DSTACK_AWS_EC2_SUBNET")
        self.credentials = credentials

    def load(self, path: Path = get_config_path()):
        if path.exists():
            with path.open() as f:
                config_data = yaml.load(f, Loader=yaml.FullLoader)
                if config_data.get("backend") != "aws":
                    raise ConfigError(f"It's not AWS config")
                if not config_data.get("bucket"):
                    raise Exception(f"For AWS backend:the bucket field is required")
                self.profile_name = config_data.get("profile") or os.getenv("AWS_PROFILE")
                self.region_name = config_data.get("region") or os.getenv("AWS_DEFAULT_REGION")
                self.bucket_name = config_data["bucket"]
                self.subnet_id = config_data.get("subnet")
        else:
            raise ConfigError()

    def save(self, path: Path = get_config_path()):
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        with path.open("w+") as f:
            f.write(self.serialize_yaml())

    def serialize(self) -> Dict:
        config_data = {
            "backend": "aws",
            "bucket": self.bucket_name,
        }
        if self.region_name:
            config_data["region"] = self.region_name
        if self.profile_name:
            config_data["profile"] = self.profile_name
        if self.subnet_id:
            config_data["subnet"] = self.subnet_id
        return config_data

    def serialize_yaml(self) -> str:
        return yaml.dump(self.serialize())

    def serialize_json(self) -> str:
        return json.dumps(self.serialize())

    @classmethod
    def deserialize(cls, config_data: Dict, auth_data: Dict = None) -> Optional["AWSConfig"]:
        bucket_name = config_data.get("bucket_name") or config_data.get("s3_bucket_name")
        region_name = config_data.get("region_name") or _DEFAULT_REGION_NAME
        profile_name = config_data.get("profile_name")
        subnet_id = (
            config_data.get("subnet_id")
            or config_data.get("ec2_subnet_id")
            or config_data.get("subnet")
        )
        return cls(
            bucket_name=bucket_name,
            region_name=region_name,
            profile_name=profile_name,
            subnet_id=subnet_id,
            credentials=auth_data,
        )

    @classmethod
    def deserialize_yaml(cls, yaml_content: str) -> Optional["AWSConfig"]:
        content = yaml.load(yaml_content, yaml.FullLoader)
        if content is None:
            return None
        return cls.deserialize(content)

    @classmethod
    def deserialize_json(cls, json_content: str) -> Optional["AWSConfig"]:
        content = json.loads(json_content)
        if content is None:
            return None
        return cls.deserialize(content)


class AWSConfigurator(Configurator):
    NAME = "aws"
    config: AWSConfig

    def get_config_from_hub_config_data(self, config_data: Dict, auth_data: Dict) -> BackendConfig:
        return AWSConfig.deserialize(config_data, auth_data)

    def register_parser(self, parser):
        aws_parser = parser.add_parser("aws", help="", formatter_class=RichHelpFormatter)
        aws_parser.add_argument("--bucket", type=str, help="", required=True)
        aws_parser.add_argument("--region", type=str, help="", required=True)
        aws_parser.add_argument(
            "--profile",
            type=str,
            help="",
        )
        aws_parser.add_argument(
            "--subnet-id",
            type=str,
            help="",
        )
        aws_parser.set_defaults(func=self._command)

    def _command(self, args: Namespace):
        config = AWSConfig()
        config.bucket_name = args.bucket
        config.region_name = args.region
        if args.profile is not None:
            config.profile_name = args.profile
        if args.subnet_id is not None:
            config.subnet_id = args.subnet_id
        config.save()
        print(f"[grey58]OK[/]")

    def configure_hub(self, config_data: Dict) -> AWSProjectValues:
        config = AWSConfig.deserialize(config_data)

        if config.region_name is not None and config.region_name not in {r[1] for r in regions}:
            raise HubConfigError(f"Invalid AWS region {config.region_name}")

        try:
            session = Session(
                region_name=config.region_name,
                aws_access_key_id=config_data.get("access_key"),
                aws_secret_access_key=config_data.get("secret_key"),
            )
            sts = session.client("sts")
            sts.get_caller_identity()
        except botocore.exceptions.ClientError:
            raise HubConfigError(
                "Credentials are not valid",
                code="invalid_credentials",
                fields=["access_key", "secret_key"],
            )

        # TODO validate config values
        project_values = AWSProjectValues()
        project_values.region_name = self._get_hub_regions(default_region=config.region_name)
        project_values.s3_bucket_name = self._get_hub_buckets(
            session=session, region=config.region_name, default_bucket=config.bucket_name
        )
        project_values.ec2_subnet_id = self._get_hub_subnet(
            session=session, default_subnet=config.subnet_id
        )
        return project_values

    def _get_hub_regions(self, default_region: Optional[str]) -> ProjectElement:
        element = ProjectElement(selected=default_region)
        for r in regions:
            element.values.append(ProjectElementValue(value=r[1], label=r[0]))
        return element

    def _get_hub_buckets(
        self, session: Session, region: str, default_bucket: Optional[str]
    ) -> AWSBucketProjectElement:
        if default_bucket is not None:
            self._validate_hub_bucket(session=session, region=region, bucket_name=default_bucket)
        element = AWSBucketProjectElement(selected=default_bucket)
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
                raise HubConfigError(
                    "The bucket belongs to another AWS region",
                    code="invalid_bucket",
                    fields=["s3_bucket_name"],
                )
        except botocore.exceptions.ClientError as e:
            if (
                hasattr(e, "response")
                and e.response.get("Error")
                and e.response["Error"].get("Code") in ["404", "403"]
            ):
                raise HubConfigError(
                    f"The bucket {bucket_name} does not exist",
                    code="invalid_bucket",
                    fields=["s3_bucket_name"],
                )
            raise e

    def _get_hub_subnet(self, session: Session, default_subnet: Optional[str]) -> ProjectElement:
        element = ProjectElement(selected=default_subnet)
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

    def configure_cli(self):
        self.config = AWSConfig()
        try:
            self.config.load()
        except ConfigError:
            pass
        default_profile_name = self.config.profile_name
        default_region_name = self.config.region_name
        default_bucket_name = self.config.bucket_name
        default_subnet_id = self.config.subnet_id

        self.config.profile_name = self._ask_profile_name(default_profile_name)
        if not default_region_name or default_profile_name != self.config.profile_name:
            try:
                my_session = boto3.session.Session(profile_name=self.config.profile_name)
                default_region_name = my_session.region_name
            except Exception:
                default_region_name = _DEFAULT_REGION_NAME
        self.config.region_name = ask_choice(
            "Choose AWS region",
            [(r[0] + " [" + r[1] + "]") for r in regions],
            [r[1] for r in regions],
            default_region_name,
        )
        if self.config.region_name != default_region_name:
            default_bucket_name = None
            default_subnet_id = None
        self.config.bucket_name = self._ask_bucket(default_bucket_name, default_subnet_id)
        self.config.subnet_id = self._ask_subnet(default_subnet_id)
        self.config.save()
        print(f"[grey58]OK[/]")

    def _s3_client(self) -> BaseClient:
        session = boto3.Session(
            profile_name=self.config.profile_name, region_name=self.config.region_name
        )
        return session.client("s3")

    def validate_bucket(self, bucket_name):
        s3_client = self._s3_client()
        try:
            response = s3_client.head_bucket(Bucket=bucket_name)
            bucket_region = response["ResponseMetadata"]["HTTPHeaders"]["x-amz-bucket-region"]
            if bucket_region != self.config.region_name:
                print(f"[red bold]✗[/red bold] [red]The bucket belongs to another AWS region.")
                return False
        except Exception as e:
            if (
                hasattr(e, "response")
                and e.response.get("Error")
                and e.response["Error"].get("Code") == "403"
            ):
                print(
                    f"[red bold]✗[/red bold] [red]You don't have access to this bucket. "
                    "It may belong to another AWS account.[/red]"
                )
                return False
            else:
                if (
                    hasattr(e, "response")
                    and e.response.get("Error")
                    and e.response["Error"].get("Code") == "404"
                ):
                    if Confirm.ask(
                        f"[sea_green3 bold]?[/sea_green3 bold] "
                        f"[red bold]The bucket doesn't exist. Create it?[/red bold]",
                        default="y",
                    ):
                        if self.config.region_name != _DEFAULT_REGION_NAME:
                            s3_client.create_bucket(
                                Bucket=bucket_name,
                                CreateBucketConfiguration={
                                    "LocationConstraint": self.config.region_name
                                },
                            )
                        else:
                            s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        return False
                else:
                    raise e
        return True

    def _ask_profile_name(self, default_profile_name):
        profiles = []
        try:
            my_session = boto3.session.Session()
            profiles.extend(my_session.available_profiles)
        except Exception:
            pass
        if len(profiles) > 1:
            if not default_profile_name:
                default_profile_name = profiles[0]
            profile_name = ask_choice(
                "Choose AWS profile", profiles, profiles, default_profile_name
            )
        elif len(profiles) == 1:
            profile_name = profiles[0]
            print(
                f"[sea_green3 bold]✓[/sea_green3 bold] [gray46]AWS profile: {profile_name}[/gray46]"
            )
        else:
            profile_name = "default"
            print(
                f"[sea_green3 bold]✓[/sea_green3 bold] [gray46]AWS profile: {profile_name}[/gray46]"
            )
        if profile_name == "default":
            profile_name = None
        return profile_name

    def _ask_bucket(self, default_bucket_name: Optional[str], default_subnet_id: Optional[str]):
        bucket_options = []
        if not default_bucket_name:
            try:
                my_session = boto3.session.Session(
                    profile_name=self.config.profile_name, region_name=self.config.region_name
                )
                sts_client = my_session.client("sts")
                account_id = sts_client.get_caller_identity()["Account"]
                default_bucket_name = f"dstack-{account_id}-{self.config.region_name}"
                bucket_options.append(f"Default [{default_bucket_name}]")
            except Exception:
                pass
        else:
            bucket_options.append(f"Default [{default_bucket_name}]")
        bucket_options.append("Custom...")
        if is_termios_available and len(bucket_options) == 2:
            from simple_term_menu import TerminalMenu

            print(
                "[sea_green3 bold]?[/sea_green3 bold] [bold]Choose S3 bucket[/bold] "
                "[gray46]Use arrows to move, type to filter[/gray46]"
            )
            bucket_menu = TerminalMenu(
                bucket_options,
                menu_cursor_style=["fg_red", "bold"],
                menu_highlight_style=["fg_red", "bold"],
                search_highlight_style=["fg_purple"],
            )
            bucket_index = bucket_menu.show()
            bucket_title = bucket_options[bucket_index].replace("[", "\\[")
            print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{bucket_title}[/grey74]")
        else:
            bucket_index = 1
        if bucket_index == 0 and default_bucket_name:
            if self.validate_bucket(default_bucket_name):
                return default_bucket_name
            else:
                return self._ask_bucket(default_bucket_name, default_subnet_id)
        else:
            return self._ask_bucket_name(default_bucket_name, default_subnet_id)

    def _ask_bucket_name(
        self, default_bucket_name: Optional[str], default_subnet_id: Optional[str]
    ):
        bucket_name = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter S3 bucket name[/bold]",
            default=default_bucket_name,
        )
        match = re.compile(r"(?!(^xn--|-s3alias$))^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$").match(
            bucket_name
        )
        if match:
            if self.validate_bucket(bucket_name):
                return bucket_name
            else:
                return self._ask_bucket(default_bucket_name, default_subnet_id)
        else:
            print(
                "[red bold]✗[/red bold] [red]Bucket name is not valid. "
                "Check naming rules: "
                "https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html[/red]"
            )
            return self._ask_bucket_name(default_bucket_name, default_subnet_id)

    def _ask_subnet(self, default_subnet_id: Optional[str]) -> Optional[str]:
        try:
            my_session = boto3.session.Session(
                profile_name=self.config.profile_name, region_name=self.config.region_name
            )
            ec2_client = my_session.client("ec2")
            subnets_response = ec2_client.describe_subnets()
        except Exception:
            return self._ask_subnet_id(default_subnet_id)
        existing_subnets = [s["SubnetId"] for s in subnets_response["Subnets"]]
        subnet_options = ["Default [no preference]"]
        subnet_options.extend(
            [(s["SubnetId"] + " [" + s["VpcId"] + "]") for s in subnets_response["Subnets"]]
        )
        choice = ask_choice(
            "Choose EC2 subnet",
            subnet_options,
            ["none"] + existing_subnets,
            default_subnet_id or "none",
            show_choices=True,
        )
        if choice == "none":
            choice = None
        return choice

    @staticmethod
    def _ask_subnet_id(default_subnet_id: Optional[str]) -> Optional[str]:
        subnet_id = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter EC2 subnet ID[/bold]",
            default=default_subnet_id or "no preference",
        )
        if subnet_id == "no preference":
            subnet_id = None
        return subnet_id
