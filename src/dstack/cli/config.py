import re
from argparse import Namespace
from typing import Optional

import boto3
from rich import print
from rich.prompt import Prompt
from simple_term_menu import TerminalMenu

from dstack.backend import load_backend
from dstack.config import load_config, ConfigError, write_config, Config, AwsBackendConfig

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


def ask_region(default_region_name):
    print("[sea_green3 bold]?[/sea_green3 bold] [bold]Choose AWS region[/bold] "
          "[gray46]Use arrows to move, type to filter[/gray46]")
    region_options = [(r[0] + " [" + r[1] + "]") for r in regions]
    default_region_index = [r[1] for r in regions].index(default_region_name) if default_region_name else None
    region_menu = TerminalMenu(region_options, menu_cursor_style=["fg_red", "bold"],
                               menu_highlight_style=["fg_red", "bold"],
                               search_key=None,
                               search_highlight_style=["fg_purple"],
                               cursor_index=default_region_index)
    region_index = region_menu.show()
    region_title = regions[region_index][0]
    region_name = regions[region_index][1]
    print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{region_title} \\[{region_name}][/grey74]")
    return region_name


def ask_subnet(profile_name: Optional[str], region_name: str, default_subnet_id: Optional[str]) -> Optional[str]:
    my_session = boto3.session.Session(profile_name=profile_name, region_name=region_name)
    ec2_client = my_session.client("ec2")
    print("[sea_green3 bold]?[/sea_green3 bold] [bold]Choose EC2 subnet[/bold] "
          "[gray46]Use arrows to move, type to filter[/gray46]")
    subnets_response = ec2_client.describe_subnets()
    existing_subnets = [s["SubnetId"] for s in subnets_response["Subnets"]]
    default_subnet_index = existing_subnets.index(
        default_subnet_id) + 1 if default_subnet_id in existing_subnets else 0
    subnet_options = ["Default [no preference]"]
    subnet_options.extend([(s["SubnetId"] + " [" + s["VpcId"] + "]") for s in subnets_response["Subnets"]])
    subnet_menu = TerminalMenu(subnet_options, menu_cursor_style=["fg_red", "bold"],
                               menu_highlight_style=["fg_red", "bold"],
                               search_key=None,
                               search_highlight_style=["fg_purple"],
                               cursor_index=default_subnet_index)
    subnet_index = subnet_menu.show()
    subnet_title = subnet_options[subnet_index].replace("[", "\\[")
    print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{subnet_title}[/grey74]")
    if subnet_index > 0:
        return existing_subnets[subnet_index - 1]
    else:
        return None


def config_func(args: Namespace):
    default_bucket_name = None
    default_region_name = None
    default_subnet_id = None
    try:
        config = load_config()
        default_region_name = config.backend_config.region_name
        default_bucket_name = config.backend_config.bucket_name
        default_subnet_id = config.backend_config.subnet_id
    except ConfigError:
        pass
    profile_name = args.profile_name
    if profile_name == "default":
        profile_name = None
    if not default_region_name:
        try:
            my_session = boto3.session.Session(profile_name=profile_name)
            default_region_name = my_session.region_name
        except Exception:
            default_region_name = "us-east-1"
    region_name = ask_region(default_region_name)
    if region_name != default_region_name:
        default_bucket_name = None
        default_subnet_id = None
    bucket_name = ask_bucket(profile_name, region_name, default_bucket_name, default_subnet_id)
    subnet_id = ask_subnet(profile_name, region_name, default_subnet_id)
    config = Config(AwsBackendConfig(profile_name, region_name, bucket_name, subnet_id))
    backend = load_backend(config)
    backend.configure()
    write_config(config)
    print(f"[grey58]OK[/]")


def ask_bucket(profile_name: Optional[str], region_name: str, default_bucket_name: Optional[str],
               default_subnet_id: Optional[str]):
    print("[sea_green3 bold]?[/sea_green3 bold] [bold]Choose S3 bucket[/bold] "
          "[gray46]Use arrows to move, type to filter[/gray46]")
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
    bucket_menu = TerminalMenu(bucket_options, menu_cursor_style=["fg_red", "bold"],
                               menu_highlight_style=["fg_red", "bold"],
                               search_highlight_style=["fg_purple"])
    bucket_index = bucket_menu.show()
    bucket_title = bucket_options[bucket_index].replace("[", "\\[")
    print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{bucket_title}[/grey74]")
    if bucket_index == 0 and default_bucket_name:
        bucket_name = default_bucket_name
        config = Config(AwsBackendConfig(profile_name, region_name, bucket_name, default_subnet_id))
        backend = load_backend(config)
        if backend.validate_bucket():
            return bucket_name
        else:
            return ask_bucket(profile_name, region_name, default_bucket_name, default_subnet_id)
    else:
        return ask_bucket_name(profile_name, region_name, None, default_subnet_id)


def ask_bucket_name(profile_name: Optional[str], region_name: str, default_bucket_name: Optional[str],
                    default_subnet_id: Optional[str]):
    bucket_name = Prompt.ask("[sea_green3 bold]?[/sea_green3 bold] [bold]Enter S3 bucket name[/bold]")
    match = re.compile(r"(?!(^xn--|-s3alias$))^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$").match(bucket_name)
    if match:
        config = Config(AwsBackendConfig(profile_name, region_name, bucket_name, default_subnet_id))
        backend = load_backend(config)
        if backend.validate_bucket():
            return bucket_name
        else:
            return ask_bucket(profile_name, region_name, default_bucket_name, default_subnet_id)
    else:
        print("[red bold]✗[/red bold] [red]Bucket name is not valid. "
              "Check naming rules: "
              "https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html[/red]")
        return ask_bucket_name(profile_name, region_name, default_bucket_name, default_subnet_id)


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("config", help="Configure the backend")
    parser.add_argument("--aws-profile", metavar="NAME",
                        help="A name of the AWS profile. Default is \"default\".", type=str,
                        dest="profile_name", default="default")
    parser.set_defaults(func=config_func)
