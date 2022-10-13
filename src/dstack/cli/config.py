import re
from argparse import Namespace
from importlib.util import find_spec
from typing import Optional, List

import boto3
from rich import print
from rich.prompt import Prompt

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

_is_termios_available = find_spec("termios") is not None


def ask_choice(title: str, labels: List[str], values: List[str], selected_value: Optional[str],
               show_choices: Optional[bool] = None) -> str:
    if selected_value not in values:
        selected_value = None
    if _is_termios_available:
        from simple_term_menu import TerminalMenu
        print(f"[sea_green3 bold]?[/sea_green3 bold] [bold]{title}[/bold] "
              "[gray46]Use arrows to move, type to filter[/gray46]")
        try:
            cursor_index = values.index(selected_value) if selected_value else None
        except ValueError:
            cursor_index = None
        terminal_menu = TerminalMenu(menu_entries=labels, menu_cursor_style=["fg_red", "bold"],
                                     menu_highlight_style=["fg_red", "bold"],
                                     search_key=None,
                                     search_highlight_style=["fg_purple"],
                                     cursor_index=cursor_index)
        chosen_menu_index = terminal_menu.show()
        chosen_menu_label = labels[chosen_menu_index].replace("[", "\\[")
        print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{chosen_menu_label}[/grey74]")
        return values[chosen_menu_index]
    else:
        if len(values) < 6 and show_choices is None or show_choices is True:
            return Prompt.ask(prompt=f"[sea_green3 bold]?[/sea_green3 bold] [bold]{title}[/bold]",
                              choices=values, default=selected_value)
        else:
            value = Prompt.ask(prompt=f"[sea_green3 bold]?[/sea_green3 bold] [bold]{title}[/bold]",
                               default=selected_value)
            if value in values:
                return value
            else:
                print(
                    f"[red]Please select one of the available options: \\[{', '.join(values)}][/red]")
                return ask_choice(title, labels, values, selected_value, show_choices)


def ask_subnet(profile_name: Optional[str], region_name: str, default_subnet_id: Optional[str]) -> Optional[str]:
    my_session = boto3.session.Session(profile_name=profile_name, region_name=region_name)
    ec2_client = my_session.client("ec2")
    subnets_response = ec2_client.describe_subnets()
    existing_subnets = [s["SubnetId"] for s in subnets_response["Subnets"]]
    subnet_options = ["Default [no preference]"]
    subnet_options.extend([(s["SubnetId"] + " [" + s["VpcId"] + "]") for s in subnets_response["Subnets"]])
    choice = ask_choice("Choose EC2 subnet", subnet_options, ["none"] + existing_subnets, default_subnet_id or "none",
                        show_choices=True)
    if choice == "none":
        choice = None
    return choice


def config_func(_: Namespace):
    default_profile_name = None
    default_bucket_name = None
    default_region_name = None
    default_subnet_id = None
    try:
        config = load_config()
        default_profile_name = config.backend_config.profile_name
        default_region_name = config.backend_config.region_name
        default_bucket_name = config.backend_config.bucket_name
        default_subnet_id = config.backend_config.subnet_id
    except ConfigError:
        pass
    profile_name = ask_profile_name(default_profile_name)
    if not default_region_name:
        try:
            my_session = boto3.session.Session(profile_name=profile_name)
            default_region_name = my_session.region_name
        except Exception:
            default_region_name = "us-east-1"
    region_name = ask_choice("Choose AWS region", [(r[0] + " [" + r[1] + "]") for r in regions],
                             [r[1] for r in regions], default_region_name)
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


def ask_profile_name(default_profile_name):
    profiles = []
    try:
        my_session = boto3.session.Session()
        profiles.extend(my_session.available_profiles)
    except Exception:
        pass
    if len(profiles) > 1:
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
        config = Config(AwsBackendConfig(profile_name, region_name, bucket_name, default_subnet_id))
        backend = load_backend(config)
        if backend.validate_bucket():
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
    parser.set_defaults(func=config_func)
