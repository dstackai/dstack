import argparse
import os

from dstack._internal.core.models.profiles import (
    Profile,
    ProfileRetryPolicy,
    SpotPolicy,
    parse_duration,
    parse_max_duration,
)


def register_profile_args(parser: argparse.ArgumentParser):
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
        "--max-duration", type=max_duration, dest="max_duration", metavar="DURATION"
    )
    profile_group.add_argument(
        "-b",
        "--backend",
        action="append",
        metavar="NAME",
        dest="backends",
        help="The backends that will be tried for provisioning",
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
    retry_group_exc.add_argument("--retry", action="store_const", dest="retry_policy", const=True)
    retry_group_exc.add_argument(
        "--no-retry", action="store_const", dest="retry_policy", const=False
    )
    retry_group_exc.add_argument(
        "--retry-limit", type=retry_limit, dest="retry_limit", metavar="DURATION"
    )


def apply_profile_args(args: argparse.Namespace, profile: Profile):
    if args.max_price is not None:
        profile.max_price = args.max_price
    if args.max_duration is not None:
        profile.max_duration = args.max_duration
    if args.backends:
        profile.backends = args.backends

    if args.spot_policy is not None:
        profile.spot_policy = args.spot_policy

    if args.retry_policy is not None:
        if not profile.retry_policy:
            profile.retry_policy = ProfileRetryPolicy()
        profile.retry_policy.retry = args.retry_policy
    elif args.retry_limit is not None:
        if not profile.retry_policy:
            profile.retry_policy = ProfileRetryPolicy()
        profile.retry_policy.retry = True
        profile.retry_policy.limit = args.retry_limit


def max_duration(v: str) -> int:
    return parse_max_duration(v)


def retry_limit(v: str) -> int:
    return parse_duration(v)
