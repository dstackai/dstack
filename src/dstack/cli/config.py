import re
from argparse import Namespace

import boto3
from rich import print
from rich.prompt import Prompt

from dstack.backend import load_backend
from dstack.config import load_config, ConfigError, write_config, Config, AwsBackendConfig


def config_func(args: Namespace):
    default_bucket_name = None
    default_region_name = None
    try:
        config = load_config()
        default_region_name = config.backend_config.region_name
        default_bucket_name = config.backend_config.bucket_name
    except ConfigError:
        pass
    print("Configure AWS backend:\n")
    profile_name = args.profile_name
    if profile_name == "default":
        profile_name = None
    if not default_region_name:
        try:
            my_session = boto3.session.Session(profile_name=profile_name)
            default_region_name = my_session.region_name
        except Exception:
            default_region_name = "us-east-1"
    region_name = Prompt.ask("Region name", default=default_region_name)
    if not default_bucket_name:
        try:
            my_session = boto3.session.Session(profile_name=profile_name, region_name=region_name)
            sts_client = my_session.client("sts")
            account_id = sts_client.get_caller_identity()["Account"]
            default_bucket_name = f"dstack-{account_id}-{region_name}"
        except Exception:
            pass
    bucket_name = ask_bucket_name(default_bucket_name)
    config = Config(AwsBackendConfig(bucket_name, region_name, profile_name))
    backend = load_backend(config)
    if backend.configure(silent=False):
        write_config(config)
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
    parser.add_argument("--aws-profile", metavar="NAME",
                        help="A name of the AWS profile. Default is \"default\".", type=str,
                        dest="profile_name", default="default")
    parser.set_defaults(func=config_func)
