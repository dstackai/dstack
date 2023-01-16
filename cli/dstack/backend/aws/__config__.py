import os
import boto3
import yaml
import re

from typing import Optional
from pathlib import Path
from rich.prompt import Prompt

from dstack.core.config import BackendConfig, get_config_path
from dstack.cli.common import ask_choice, _is_termios_available

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


def validate_bucket():
    raise Exception("Not implement")  # TODO Max priority


def _ask_profile_name(default_profile_name):
    profiles = []
    try:
        my_session = boto3.session.Session()
        profiles.extend(my_session.available_profiles)
    except Exception:
        pass
    if len(profiles) > 1:
        if not default_profile_name:
            default_profile_name = profiles[0]
        profile_name = ask_choice("Choose AWS profile", profiles, profiles, default_profile_name)
    elif len(profiles) == 1:
        profile_name = profiles[0]
        print(f"[sea_green3 bold]✓[/sea_green3 bold] [gray46]AWS profile: {profile_name}[/gray46]")
    else:
        profile_name = "default"
        print(f"[sea_green3 bold]✓[/sea_green3 bold] [gray46]AWS profile: {profile_name}[/gray46]")
    if profile_name == "default":
        profile_name = None
    return profile_name


def ask_bucket(profile_name: Optional[str], region_name: str, default_bucket_name: Optional[str],
               default_subnet_id: Optional[str]):
    bucket_options = []
    if not default_bucket_name:
        try:
            my_session = boto3.session.Session(profile_name=profile_name, region_name=region_name)
            sts_client = my_session.client("sts")
            account_id = sts_client.get_caller_identity()["Account"]
            default_bucket_name = f"dstack-{account_id}-{region_name}"
            bucket_options.append(f"Default [{default_bucket_name}]")
        except Exception:
            pass
    else:
        bucket_options.append(f"Default [{default_bucket_name}]")
    bucket_options.append("Custom...")
    if _is_termios_available and len(bucket_options) == 2:
        from simple_term_menu import TerminalMenu
        print("[sea_green3 bold]?[/sea_green3 bold] [bold]Choose S3 bucket[/bold] "
              "[gray46]Use arrows to move, type to filter[/gray46]")
        bucket_menu = TerminalMenu(bucket_options, menu_cursor_style=["fg_red", "bold"],
                                   menu_highlight_style=["fg_red", "bold"],
                                   search_highlight_style=["fg_purple"])
        bucket_index = bucket_menu.show()
        bucket_title = bucket_options[bucket_index].replace("[", "\\[")
        print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{bucket_title}[/grey74]")
    else:
        bucket_index = 1
    if bucket_index == 0 and default_bucket_name:
        bucket_name = default_bucket_name
        if validate_bucket():
            return bucket_name
        else:
            return ask_bucket(profile_name, region_name, default_bucket_name, default_subnet_id)
    else:
        return ask_bucket_name(profile_name, region_name, default_bucket_name, default_subnet_id)


def ask_bucket_name(profile_name: Optional[str], region_name: str, default_bucket_name: Optional[str],
                    default_subnet_id: Optional[str]):
    bucket_name = Prompt.ask("[sea_green3 bold]?[/sea_green3 bold] [bold]Enter S3 bucket name[/bold]",
                             default=default_bucket_name)
    match = re.compile(r"(?!(^xn--|-s3alias$))^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$").match(bucket_name)
    if match:
        if validate_bucket():
            return bucket_name
        else:
            return ask_bucket(profile_name, region_name, default_bucket_name, default_subnet_id)
    else:
        print("[red bold]✗[/red bold] [red]Bucket name is not valid. "
              "Check naming rules: "
              "https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html[/red]")
        return ask_bucket_name(profile_name, region_name, default_bucket_name, default_subnet_id)


def ask_subnet(profile_name: Optional[str], region_name: str, default_subnet_id: Optional[str]) -> Optional[str]:
    try:
        my_session = boto3.session.Session(profile_name=profile_name, region_name=region_name)
        ec2_client = my_session.client("ec2")
        subnets_response = ec2_client.describe_subnets()
    except Exception:
        return ask_subnet_id(default_subnet_id)
    existing_subnets = [s["SubnetId"] for s in subnets_response["Subnets"]]
    subnet_options = ["Default [no preference]"]
    subnet_options.extend([(s["SubnetId"] + " [" + s["VpcId"] + "]") for s in subnets_response["Subnets"]])
    choice = ask_choice("Choose EC2 subnet", subnet_options, ["none"] + existing_subnets,
                        default_subnet_id or "none", show_choices=True)
    if choice == "none":
        choice = None
    return choice


def ask_subnet_id(default_subnet_id: Optional[str]) -> Optional[str]:
    subnet_id = Prompt.ask("[sea_green3 bold]?[/sea_green3 bold] [bold]Enter EC2 subnet ID[/bold]",
                           default=default_subnet_id or "no preference")
    if subnet_id == "no preference":
        subnet_id = None
    return subnet_id


class AWSConfig(BackendConfig):
    NAME = 'aws'

    _configured = True

    def __init__(self):
        super().__init__()
        self.bucket_name = os.getenv("DSTACK_AWS_S3_BUCKET") or None
        self.region_name = os.getenv("DSTACK_AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or None
        self.profile_name = os.getenv("DSTACK_AWS_PROFILE") or os.getenv("AWS_PROFILE") or None
        self.subnet_id = os.getenv("DSTACK_AWS_EC2_SUBNET") or None

    def load(self, path: Path = get_config_path()):
        if path.exists():
            with path.open() as f:
                config_data = yaml.load(f, Loader=yaml.FullLoader)
                if config_data.get("backend") != self.NAME:
                    raise Exception(f"It's not AWS config")
                if not config_data.get("bucket"):
                    raise Exception(f"For AWS backend:the bucket field is required")
                self.profile_name = config_data.get("profile") or os.getenv("AWS_PROFILE")
                self.region_name = config_data.get("region") or os.getenv("AWS_DEFAULT_REGION")
                self.bucket_name = config_data["bucket"]
                self.subnet_id = config_data.get("subnet")
        else:
            self.profile_name = os.getenv("DSTACK_AWS_PROFILE") or os.getenv("AWS_PROFILE")
            self.region_name = os.getenv("DSTACK_AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
            self.bucket_name = ""
            self.subnet_id = os.getenv("DSTACK_AWS_EC2_SUBNET")

    def save(self, path: Path = get_config_path()):
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        with path.open('w') as f:
            config_data = {
                "backend": self.NAME,
                "bucket": self.bucket_name
            }
            if self.region_name:
                config_data["region"] = self.region_name
            if self.profile_name:
                config_data["profile"] = self.profile_name
            if self.subnet_id:
                config_data["subnet"] = self.subnet_id
            yaml.dump(config_data, f)

    def configure(self):

        self.load()
        default_profile_name = self.profile_name
        default_region_name = self.region_name
        default_bucket_name = self.bucket_name
        default_subnet_id = self.subnet_id

        self.profile_name = _ask_profile_name(default_profile_name)
        if not default_region_name or default_profile_name != self.profile_name:
            try:
                my_session = boto3.session.Session(profile_name=self.profile_name)
                default_region_name = my_session.region_name
            except Exception:
                default_region_name = "us-east-1"
        self.region_name = ask_choice("Choose AWS region", [(r[0] + " [" + r[1] + "]") for r in regions],
                                      [r[1] for r in regions], default_region_name)
        if self.region_name != default_region_name:
            default_bucket_name = None
            default_subnet_id = None
        self.bucket_name = ask_bucket(self.profile_name, self.region_name, default_bucket_name, default_subnet_id)
        self.subnet_id = ask_subnet(self.profile_name, self.region_name, default_subnet_id)
        self.save()
        print(f"[grey58]OK[/]")
