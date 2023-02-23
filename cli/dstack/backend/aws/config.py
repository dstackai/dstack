import os
import re
from pathlib import Path
from typing import Optional

import boto3
import yaml
from botocore.client import BaseClient
from rich import print
from rich.prompt import Confirm, Prompt

from dstack.cli.common import _is_termios_available, ask_choice
from dstack.core.config import BackendConfig, get_config_path
from dstack.core.error import ConfigError

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


class AWSConfig(BackendConfig):
    NAME = "aws"

    _configured = True

    bucket_name = None
    region_name = None
    profile_name = None
    subnet_id = None

    def __init__(self):
        super().__init__()
        self.bucket_name = os.getenv("DSTACK_AWS_S3_BUCKET") or None
        self.region_name = (
            os.getenv("DSTACK_AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or None
        )
        self.profile_name = os.getenv("DSTACK_AWS_PROFILE") or os.getenv("AWS_PROFILE") or None
        self.subnet_id = os.getenv("DSTACK_AWS_EC2_SUBNET") or None

    def load(self, path: Path = get_config_path()):
        if path.exists():
            with path.open() as f:
                config_data = yaml.load(f, Loader=yaml.FullLoader)
                if config_data.get("backend") != self.NAME:
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
        with path.open("w") as f:
            config_data = {"backend": self.NAME, "bucket": self.bucket_name}
            if self.region_name:
                config_data["region"] = self.region_name
            if self.profile_name:
                config_data["profile"] = self.profile_name
            if self.subnet_id:
                config_data["subnet"] = self.subnet_id
            yaml.dump(config_data, f)

    def configure(self):
        try:
            self.load()
        except ConfigError:
            pass
        default_profile_name = self.profile_name
        default_region_name = self.region_name
        default_bucket_name = self.bucket_name
        default_subnet_id = self.subnet_id

        self.profile_name = self._ask_profile_name(default_profile_name)
        if not default_region_name or default_profile_name != self.profile_name:
            try:
                my_session = boto3.session.Session(profile_name=self.profile_name)
                default_region_name = my_session.region_name
            except Exception:
                default_region_name = "us-east-1"
        self.region_name = ask_choice(
            "Choose AWS region",
            [(r[0] + " [" + r[1] + "]") for r in regions],
            [r[1] for r in regions],
            default_region_name,
        )
        if self.region_name != default_region_name:
            default_bucket_name = None
            default_subnet_id = None
        self.bucket_name = self.ask_bucket(default_bucket_name, default_subnet_id)
        self.subnet_id = self.ask_subnet(default_subnet_id)
        self.save()
        print(f"[grey58]OK[/]")

    def _s3_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.profile_name, region_name=self.region_name)
        return session.client("s3")

    def validate_bucket(self, bucket_name):
        s3_client = self._s3_client()
        try:
            response = s3_client.head_bucket(Bucket=bucket_name)
            bucket_region = response["ResponseMetadata"]["HTTPHeaders"]["x-amz-bucket-region"]
            if bucket_region != self.region_name:
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
                        if self.region_name != "us-east-1":
                            s3_client.create_bucket(
                                Bucket=bucket_name,
                                CreateBucketConfiguration={"LocationConstraint": self.region_name},
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

    def ask_bucket(self, default_bucket_name: Optional[str], default_subnet_id: Optional[str]):
        bucket_options = []
        if not default_bucket_name:
            try:
                my_session = boto3.session.Session(
                    profile_name=self.profile_name, region_name=self.region_name
                )
                sts_client = my_session.client("sts")
                account_id = sts_client.get_caller_identity()["Account"]
                default_bucket_name = f"dstack-{account_id}-{self.region_name}"
                bucket_options.append(f"Default [{default_bucket_name}]")
            except Exception:
                pass
        else:
            bucket_options.append(f"Default [{default_bucket_name}]")
        bucket_options.append("Custom...")
        if _is_termios_available and len(bucket_options) == 2:
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
                return self.ask_bucket(default_bucket_name, default_subnet_id)
        else:
            return self.ask_bucket_name(default_bucket_name, default_subnet_id)

    def ask_bucket_name(
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
                return self.ask_bucket(default_bucket_name, default_subnet_id)
        else:
            print(
                "[red bold]✗[/red bold] [red]Bucket name is not valid. "
                "Check naming rules: "
                "https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html[/red]"
            )
            return self.ask_bucket_name(default_bucket_name, default_subnet_id)

    def ask_subnet(self, default_subnet_id: Optional[str]) -> Optional[str]:
        try:
            my_session = boto3.session.Session(
                profile_name=self.profile_name, region_name=self.region_name
            )
            ec2_client = my_session.client("ec2")
            subnets_response = ec2_client.describe_subnets()
        except Exception:
            return self.ask_subnet_id(default_subnet_id)
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
    def ask_subnet_id(default_subnet_id: Optional[str]) -> Optional[str]:
        subnet_id = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter EC2 subnet ID[/bold]",
            default=default_subnet_id or "no preference",
        )
        if subnet_id == "no preference":
            subnet_id = None
        return subnet_id
