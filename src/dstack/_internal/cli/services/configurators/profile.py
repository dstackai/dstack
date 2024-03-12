import argparse
import os

from dstack._internal.core.models.profiles import (
    DEFAULT_INSTANCE_RETRY_DURATION,
    DEFAULT_POOL_TERMINATION_IDLE_TIME,
    CreationPolicy,
    Profile,
    ProfileRetryPolicy,
    SpotPolicy,
    TerminationPolicy,
    parse_duration,
    parse_max_duration,
)


def register_profile_args(parser: argparse.ArgumentParser, pool_add: bool = False):
    """
    Registers `parser` with `dstack run` and `dstack pool add`
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
    if not pool_add:
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
    if pool_add:
        pools_group_exc = parser
    else:
        pools_group = parser.add_argument_group("Pools")
        pools_group_exc = pools_group.add_mutually_exclusive_group()
    pools_group_exc.add_argument(
        "--pool",
        dest="pool_name",
        help="The name of the pool. If not set, the default pool will be used",
    )
    pools_group_exc.add_argument(
        "--reuse",
        dest="creation_policy_reuse",
        action="store_true",
        help="Reuse instance from pool",
    )
    pools_group_exc.add_argument(
        "--dont-destroy",
        dest="dont_destroy",
        action="store_true",
        help="Do not destroy instance after the run is finished",
    )
    pools_group_exc.add_argument(
        "--idle-duration",
        dest="idle_duration",
        type=str,
        help="Time to wait before destroying the idle instance",
    )
    if not pool_add:
        pools_group_exc.add_argument(
            "--instance",
            dest="instance_name",
            metavar="NAME",
            help="Reuse instance from pool with name [code]NAME[/]",
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
        "--retry-duration", type=retry_duration, dest="retry_duration", metavar="DURATION"
    )


def apply_profile_args(args: argparse.Namespace, profile: Profile, pool_add: bool = False):
    """
    Overrides `profile` settings with arguments registered by `register_profile_args()`.
    """
    # TODO: Re-assigned profile attributes are not validated by pydantic.
    # So the validation will only be done by the server.
    # Consider setting validate_assignment=True for modified pydantic models.
    if args.backends:
        profile.backends = args.backends
    if args.regions:
        profile.regions = args.regions
    if args.instance_types:
        profile.instance_types = args.instance_types
    if args.max_price is not None:
        profile.max_price = args.max_price
    if not pool_add:
        if args.max_duration is not None:
            profile.max_duration = args.max_duration

    if args.pool_name:
        profile.pool_name = args.pool_name

    if args.idle_duration is not None:
        profile.termination_idle_time = args.idle_duration
    if pool_add and args.idle_duration is None:
        profile.termination_idle_time = DEFAULT_POOL_TERMINATION_IDLE_TIME

    if args.dont_destroy:
        profile.termination_policy = TerminationPolicy.DONT_DESTROY
    if not pool_add:
        if args.instance_name:
            profile.instance_name = args.instance_name
        if args.creation_policy_reuse:
            profile.creation_policy = CreationPolicy.REUSE

    if args.spot_policy is not None:
        profile.spot_policy = args.spot_policy
    if pool_add and args.spot_policy is None:  # ONDEMAND by default for `dstack pool add`
        profile.spot_policy = SpotPolicy.ONDEMAND

    if not pool_add:
        if args.retry_policy is not None:
            if not profile.retry_policy:
                profile.retry_policy = ProfileRetryPolicy()
            profile.retry_policy.retry = args.retry_policy
        elif args.retry_duration is not None:
            if not profile.retry_policy:
                profile.retry_policy = ProfileRetryPolicy()
            profile.retry_policy.retry = True
            profile.retry_policy.limit = args.retry_duration
    else:
        if args.retry_policy is not None:
            if not profile.retry_policy:
                profile.retry_policy = ProfileRetryPolicy()
            profile.retry_policy.retry = args.retry_policy
            if profile.retry_policy.retry:
                profile.retry_policy.limit = DEFAULT_INSTANCE_RETRY_DURATION
        elif args.retry_duration is not None:
            if not profile.retry_policy:
                profile.retry_policy = ProfileRetryPolicy()
            profile.retry_policy.retry = True
            profile.retry_policy.limit = args.retry_duration  # --retry-duration


def max_duration(v: str) -> int:
    return parse_max_duration(v)


def retry_duration(v: str) -> int:
    return parse_duration(v)
