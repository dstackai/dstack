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
    bucket_name = Prompt.ask("S3 bucket name", default=bucket_name)
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


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("config", help="Configure the backend")
    parser.set_defaults(func=config_func)
