from argparse import Namespace

import colorama
import requests

from dstack.cli import get_or_ask, confirm
from dstack.server import __server_url__
from dstack.config import _get_config_path, from_yaml_file, Profile


def login_func(args: Namespace):
    dstack_config = from_yaml_file(_get_config_path(None))
    # TODO: Support non-default profiles
    profile = dstack_config.get_profile("default")
    if profile is None:
        profile = Profile("default", None, args.server, not args.no_verify)

    if args.server is not None:
        profile.server = args.server
    profile.verify = not args.no_verify

    user = get_or_ask(args, None, "user", "Username: ", secure=False)
    password = get_or_ask(args, None, "password", "Password: ", secure=True)

    login_params = {
        "user": user,
        "password": password
    }
    headers = {
        "Content-Type": f"application/json; charset=utf-8"
    }
    login_response = requests.request(method="GET", url=f"{profile.server}/users/login", params=login_params,
                                      headers=headers,
                                      verify=profile.verify)
    if login_response.status_code == 200:
        token = login_response.json()["token"]
        profile.token = token

        dstack_config.add_or_replace_profile(profile)
        dstack_config.save()
        print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
    else:
        response_json = login_response.json()
        if response_json.get("message") is not None:
            print(response_json["message"])
        else:
            login_response.raise_for_status()


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("login", help="Log in")

    parser.add_argument("-u", "--user", help="Set a username", type=str, nargs="?")
    parser.add_argument("-p", "--password", help="Set a user password", type=str, nargs="?")

    parser.add_argument("--server", help="Set a server endpoint", type=str, nargs="?",
                        default=__server_url__, const=__server_url__)
    parser.add_argument("--no-verify", help="Do not verify SSL certificates", dest="no_verify", action="store_true")

    parser.set_defaults(func=login_func)
