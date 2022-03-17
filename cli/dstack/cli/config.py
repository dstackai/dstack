from argparse import Namespace
from pathlib import Path

from dstack.cli import confirm, get_or_ask
from dstack.server import __server_url__
from dstack.config import from_yaml_file, _get_config_path, Profile
from dstack.logger import hide_token


def list_profiles(args: Namespace):
    conf = from_yaml_file(_get_config_path(args.file))
    profiles = conf.list_profiles()
    print("list of available profiles:\n")
    for name in profiles:
        profile = profiles[name]
        print(f"{name}:")
        print(f"\ttoken: {hide_token(profile.token)}")
        if profile.server != __server_url__:
            print(f"\t\tserver: {profile.server}")


def remove_profile(args: Namespace):
    conf = from_yaml_file(_get_config_path(args.file))

    if args.force or confirm(f"Do you want to delete profile '{args.profile}'"):
        conf.remove_profile(args.profile)

    conf.save()


def add_or_modify_profile(args: Namespace):
    file = Path(args.file) if args.file else None
    conf = from_yaml_file(_get_config_path(file))
    profile = conf.get_profile(args.profile)

    token = get_or_ask(args, profile, "token", "Token: ", secure=True)

    if profile is None:
        profile = Profile(args.profile, token, args.server, not args.no_verify)
    elif args.force or (token != profile.token and confirm(
            f"Do you want to replace the token for the profile '{args.profile}'")):
        profile.token = token

    profile.server = args.server
    profile.verify = not args.no_verify

    conf.add_or_replace_profile(profile)
    conf.save()


def register_parsers(main_subparsers):
    def add_common_arguments(command_parser):
        add_profile_argument(command_parser)
        command_parser.add_argument("--token", help="Set a personal access token", type=str, nargs="?")
        command_parser.add_argument("--server", help="Set a server endpoint, by default is " + __server_url__,
                                    type=str, nargs="?", default=__server_url__, const=__server_url__)
        command_parser.add_argument("--no-verify", help="Do not verify SSL certificates", dest="no_verify",
                                    action="store_true")

    def add_force_argument(command_parser):
        command_parser.add_argument("--force", help="Don't ask for confirmation", action="store_true")

    def add_file_argument(command_parser):
        command_parser.add_argument("--file", help="Use specific config file")

    def add_profile_argument(command_parser):
        command_parser.add_argument("profile", metavar="PROFILE", help="Set a profile name", type=str,
                                    default="default", nargs="?")

    parser = main_subparsers.add_parser("config", help="Manage configuration")
    add_common_arguments(parser)
    add_force_argument(parser)
    add_file_argument(parser)
    parser.set_defaults(func=add_or_modify_profile)

    subparsers = parser.add_subparsers()

    remove_parser = subparsers.add_parser("delete", help="delete existing profile")
    add_profile_argument(remove_parser)
    add_force_argument(remove_parser)
    add_file_argument(remove_parser)
    remove_parser.set_defaults(func=remove_profile)

    list_parser = subparsers.add_parser("list", help="list configured profiles")
    add_file_argument(list_parser)
    list_parser.set_defaults(func=list_profiles)
