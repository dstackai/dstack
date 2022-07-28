import sys
from argparse import Namespace

from rich import print
from rich.prompt import Confirm

from dstack.cli import get_or_ask
from dstack.cli.common import do_post, sensitive, get_user_info
from dstack.config import ConfigurationError, get_config


def config_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        user_info = get_user_info(profile)
        data = {
            "aws_access_key_id": get_or_ask(args, None, "aws_access_key_id", "AWS Access Key ID", secure=True),
            "aws_secret_access_key": get_or_ask(args, None, "aws_secret_access_key", "AWS Secret Access Key",
                                                secure=True),
            "aws_region":
                get_or_ask(args, None, "aws_region", f"Region name", secure=False, required=False,
                           default=user_info['default_configuration']['aws_region']),
            "artifacts_s3_bucket": get_or_ask(args, None, "artifacts_s3_bucket", "Artifacts S3 bucket",
                                              secure=False, required=False, default="None")
        }
        response = do_post("users/aws/info")
        if response.status_code == 200:
            response_json = response.json()
            if response_json.get("aws_access_key_id") is None \
                    and response_json.get("aws_secret_access_key") is None \
                    and response_json.get("aws_region") is None \
                    and response_json.get("artifacts_s3_bucket") is None:
                send_aws_config_request(data)
            else:
                if args.yes or Confirm.ask(f"[red]Override the previous configuration?[/]"):
                    send_aws_config_request(data)
                else:
                    print(f"[red]Cancelled[/]")
        else:
            response.raise_for_status()
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def send_aws_config_request(data):
    response = do_post("users/aws/config", data)
    if response.status_code == 200:
        print(f"[grey58]OK[/]")
    if response.status_code == 400 and response.json().get("message") == "non-cancelled requests":
        sys.exit(f"Call 'dstack autoscale clear' first")
    else:
        response.raise_for_status()


def info_func(_: Namespace):
    try:
        response = do_post("users/aws/info")
        if response.status_code == 200:
            response_json = response.json()
            print(f"[magenta]AWS Access Key ID[/]: " + (
                    sensitive(response_json.get("aws_access_key_id")) or "None"))
            print(f"[magenta]AWS Secret Access Key[/]: " + (
                    sensitive(response_json.get("aws_secret_access_key")) or "None"))
            print(f"[magenta]Region name[/]: " + (
                    response_json.get("aws_region") or "None"))
            print(f"[magenta]Artifacts S3 bucket[/]: " + (
                    response_json.get("artifacts_s3_bucket") or "<none>"))
        else:
            response.raise_for_status()
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def clear_func(args: Namespace):
    try:
        response = do_post("users/aws/info")
        if response.status_code == 200:
            response_json = response.json()
            if response_json.get("aws_access_key_id") is None \
                    and response_json.get("aws_secret_access_key") is None \
                    and response_json.get("aws_region") is None \
                    and response_json.get("artifacts_s3_bucket") is None:
                do_clear_request()
            else:
                if args.yes or Confirm.ask("[red]Override the previous configuration?[/]"):
                    do_clear_request()
                else:
                    print(f"[red]Cancelled[/]")
        else:
            response.raise_for_status()
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def do_clear_request():
    response = do_post("users/aws/clear")
    if response.status_code == 200:
        print(f"[grey58]OK[/]")
    elif response.status_code == 400 and response.json().get("message") == "non-cancelled requests":
        sys.exit(f"Call 'dstack autoscale clear' first")
    else:
        response.raise_for_status()


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("aws", help="Manage AWS account")

    subparsers = parser.add_subparsers()

    configure_parser = subparsers.add_parser("config", help="Configure own AWS account")
    configure_parser.add_argument("--aws-access-key-id", type=str, dest="aws_access_key_id")
    configure_parser.add_argument("--aws-secret-access-key", type=str, dest="aws_secret_access_key")
    configure_parser.add_argument("--aws-region", type=str, dest="aws_region")
    configure_parser.add_argument("--artifacts-s3-bucket", type=str, dest="artifacts_s3_bucket", nargs='?',
                                  const="", action='store')
    configure_parser.add_argument("--yes", "-y", help="Don't ask for confirmation", action="store_true")
    configure_parser.set_defaults(func=config_func)

    info_parser = subparsers.add_parser("info", help="Display the current configuration")
    info_parser.set_defaults(func=info_func)

    clear_parser = subparsers.add_parser("clear", help="Clear the current configuration")
    clear_parser.set_defaults(func=clear_func)
    clear_parser.add_argument("--yes", "-y", help="Don't ask for confirmation", action="store_true")
