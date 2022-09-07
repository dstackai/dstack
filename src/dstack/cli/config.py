import re
from argparse import Namespace

import boto3
from rich import print
from rich.prompt import Prompt

from dstack.backend import load_backend
from dstack.config import load_config, ConfigError, write_config, Config, AwsBackendConfig


def config_func(_: Namespace):
    bucket_name = None
    region_name = None
    profile_name = None
    try:
        config = load_config()
        bucket_name = config.backend_config.bucket_name
        profile_name = config.backend_config.profile_name
        region_name = config.backend_config.region_name
    except ConfigError:
        pass
    print("Configure AWS backend:\n")
    profile_name = Prompt.ask("AWS profile name", default=profile_name or "default")
    if profile_name == "default":
        profile_name = None
    bucket_name = ask_bucket_name(bucket_name)
    if not region_name:
        try:
            my_session = boto3.session.Session(profile_name=profile_name)
            region_name = my_session.region_name
        except Exception:
            region_name = None
    region_name = Prompt.ask("Region name", default=region_name)
    write_config(Config(AwsBackendConfig(bucket_name, region_name, profile_name)))
    backend = load_backend()
    backend.configure(silent=False)
    print(f"[grey58]OK[/]")


def ask_bucket_name(default_bucket_name):
    bucket_name = Prompt.ask("S3 bucket name", default=default_bucket_name)
    match = re.compile(r"(?!(^xn--|-s3alias$))^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$").match(bucket_name)
    if match:
        return bucket_name
    else:
        print("[red]Bucket name contains invalid characters.[/red] "
              "See rules for bucket naming: "
              "https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html")
        return ask_bucket_name(default_bucket_name)


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("config", help="Configure the backend")
    parser.set_defaults(func=config_func)
