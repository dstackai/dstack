import re
from argparse import Namespace

import boto3
from rich import print
from rich.prompt import Prompt
from simple_term_menu import TerminalMenu

from dstack.backend import load_backend
from dstack.config import load_config, ConfigError, write_config, Config, AwsBackendConfig

regions = [
    ("US East, Ohio", "us-east-2"),
    ("US East, N. Virginia", "us-east-1"),
    ("US West, N. California", "us-west-1"),
    ("US West, Oregon", "us-west-2"),
    ("Canada, Central", "ca-central-1"),
    ("Europe, Frankfurt", "eu-central-1"),
    ("Europe, Ireland", "eu-west-1"),
    ("Europe, London", "eu-west-2"),
    ("Europe, Paris", "eu-west-3"),
    ("Europe, Stockholm", "eu-north-1"),
    ("Asia Pacific, Singapore", "ap-southeast-1"),
]


def ask_region(default_region_name):
    print("[sea_green3 bold]?[/sea_green3 bold] [bold]AWS region[/bold] "
          "[gray46]Use arrows to move, type to filter[/gray46]")
    region_options = [(r[0] + " [" + r[1] + "]") for r in regions]
    default_region_index = [r[1] for r in regions].index(default_region_name)
    region_menu = TerminalMenu(region_options, menu_cursor_style=["fg_red", "bold"],
                               menu_highlight_style=["fg_red", "bold"],
                               search_key=None,
                               search_highlight_style=["fg_purple"],
                               cursor_index=default_region_index)
    region_index = region_menu.show()
    region_title = regions[region_index][0]
    region_name = regions[region_index][1]
    print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{region_title} \[{region_name}][/grey74]")
    return region_name


def config_func(args: Namespace):
    default_bucket_name = None
    default_region_name = None
    try:
        config = load_config()
        default_region_name = config.backend_config.region_name
        default_bucket_name = config.backend_config.bucket_name
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
    print("[sea_green3 bold]?[/sea_green3 bold] [bold]S3 bucket[/bold] "
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
    else:
        bucket_name = ask_bucket_name(None)
    config = Config(AwsBackendConfig(bucket_name, region_name, profile_name))
    backend = load_backend(config)
    if backend.configure(silent=False):
        write_config(config)
        print(f"[grey58]OK[/]")


def ask_bucket_name(default_bucket_name):
    bucket_name = Prompt.ask("[sea_green3 bold]?[/sea_green3 bold] [bold]S3 bucket name[/bold] "
                             "[gray46](must not belong to another AWS account)[/gray46]")
    match = re.compile(r"(?!(^xn--|-s3alias$))^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$").match(bucket_name)
    if match:
        return bucket_name
    else:
        print("[red bold]✗[/red bold] [red]Bucket name is not valid. "
              "Check naming rules: "
              "https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html[/red]")
        return ask_bucket_name(default_bucket_name)


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("config", help="Configure the backend")
    parser.add_argument("--aws-profile", metavar="NAME",
                        help="A name of the AWS profile. Default is \"default\".", type=str,
                        dest="profile_name", default="default")
    parser.set_defaults(func=config_func)
