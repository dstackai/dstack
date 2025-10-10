import argparse
import os
from typing import Union

from dstack._internal.core.models.configurations import AnyRunConfiguration
from dstack._internal.core.models.profiles import (
    CreationPolicy,
    Profile,
    ProfileRetry,
    SpotPolicy,
    parse_duration,
    parse_max_duration,
)


def register_profile_args(parser: argparse.ArgumentParser):
    """
    Registers `parser` with `dstack apply` run configuration
    CLI arguments that override `profiles.yml` settings.
    """
    profile_group = parser.add_argument_group("Profile")
    profile_group.add_argument(
        "--profile",
        metavar="NAME",
        help="The name of the profile. Defaults to [code]$DSTACK_PROFILE[/]",
        default=os.getenv("DSTACK_PROFILE"),
        dest="profile",
    )
    profile_group.add_argument(
        "--max-price",
        metavar="PRICE",
        type=float,
        help="The maximum price per hour, in dollars",
        dest="max_price",
    )
    profile_group.add_argument(
        "--max-duration",
        type=max_duration,
        dest="max_duration",
        help="The maximum duration of the run",
        metavar="DURATION",
    )
    profile_group.add_argument(
        "-b",
        "--backend",
        action="append",
        metavar="NAME",
        dest="backends",
        help="The backends that will be tried for provisioning",
    )
    profile_group.add_argument(
        "-r",
        "--region",
        action="append",
        metavar="NAME",
        dest="regions",
        help="The regions that will be tried for provisioning",
    )
    profile_group.add_argument(
        "--instance-type",
        action="append",
        metavar="NAME",
        dest="instance_types",
        help="The cloud-specific instance types that will be tried for provisioning",
    )

    fleets_group = parser.add_argument_group("Fleets")
    fleets_group.add_argument(
        "--fleet",
        action="append",
        metavar="NAME",
        dest="fleets",
        help="Consider only instances from the specified fleet(s) for reuse",
    )
    fleets_group_exc = fleets_group.add_mutually_exclusive_group()
    fleets_group_exc.add_argument(
        "-R",
        "--reuse",
        dest="creation_policy_reuse",
        action="store_true",
        help="Reuse an existing instance from fleet (do not provision a new one)",
    )
    fleets_group_exc.add_argument(
        "--dont-destroy",
        dest="dont_destroy",
        action="store_true",
        help="Do not destroy instance after the run is finished (if the run provisions a new instance)",
    )
    fleets_group_exc.add_argument(
        "--idle-duration",
        dest="idle_duration",
        type=str,
        help="Time to wait before destroying the idle instance (if the run provisions a new instance)",
    )

    spot_group = parser.add_argument_group("Spot policy")
    spot_group_exc = spot_group.add_mutually_exclusive_group()
    spot_group_exc.add_argument(
        "--spot",
        action="store_const",
        dest="spot_policy",
        const=SpotPolicy.SPOT,
        help="Consider only spot instances",
    )
    spot_group_exc.add_argument(
        "--on-demand",
        action="store_const",
        dest="spot_policy",
        const=SpotPolicy.ONDEMAND,
        help="Consider only on-demand instances",
    )
    spot_group_exc.add_argument(
        "--spot-auto",
        action="store_const",
        dest="spot_policy",
        const=SpotPolicy.AUTO,
        help="Consider both spot and on-demand instances",
    )
    spot_group_exc.add_argument(
        "--spot-policy",
        type=SpotPolicy,
        dest="spot_policy",
        metavar="POLICY",
        help="One of %s" % ", ".join([f"[code]{i.value}[/]" for i in SpotPolicy]),
    )

    retry_group = parser.add_argument_group("Retry policy")
    retry_group_exc = retry_group.add_mutually_exclusive_group()
    retry_group_exc.add_argument("--retry", action="store_const", dest="retry", const=True)
    retry_group_exc.add_argument("--no-retry", action="store_const", dest="retry", const=False)
    retry_group_exc.add_argument(
        "--retry-duration", type=retry_duration, dest="retry_duration", metavar="DURATION"
    )


def apply_profile_args(
    args: argparse.Namespace,
    profile_settings: Union[Profile, AnyRunConfiguration],
):
    """
    Overrides `profile_settings` settings with arguments registered by `register_profile_args()`.
    """
    # TODO: Re-assigned profile attributes are not validated by pydantic.
    # So the validation will only be done by the server.
    # Consider setting validate_assignment=True for modified pydantic models.
    if args.backends:
        profile_settings.backends = args.backends
    if args.regions:
        profile_settings.regions = args.regions
    if args.instance_types:
        profile_settings.instance_types = args.instance_types
    if args.max_price is not None:
        profile_settings.max_price = args.max_price
    if args.max_duration is not None:
        profile_settings.max_duration = args.max_duration

    if args.fleets:
        profile_settings.fleets = args.fleets
    if args.idle_duration is not None:
        profile_settings.idle_duration = args.idle_duration
    elif args.dont_destroy:
        profile_settings.idle_duration = -1
    if args.creation_policy_reuse:
        profile_settings.creation_policy = CreationPolicy.REUSE

    if args.spot_policy is not None:
        profile_settings.spot_policy = args.spot_policy

    if args.retry is not None:
        profile_settings.retry = args.retry
    elif args.retry_duration is not None:
        profile_settings.retry = ProfileRetry(
            duration=args.retry_duration,
        )


def max_duration(v: str) -> int:
    return parse_max_duration(v)


def retry_duration(v: str) -> int:
    return parse_duration(v)
