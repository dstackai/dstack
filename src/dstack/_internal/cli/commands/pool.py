import argparse
from collections.abc import Sequence
from pathlib import Path

from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators.profile import (
    apply_profile_args,
    register_profile_args,
)
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.core.errors import CLIError, ServerClientError
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.pools import Instance, Pool
from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME, Profile
from dstack._internal.core.models.runs import Requirements
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.utils.common import pretty_date
from dstack._internal.utils.logging import get_logger
from dstack.api.utils import load_profile

logger = get_logger(__name__)
NOTSET = object()


def print_pool_table(pools: Sequence[Pool], verbose):
    table = Table(box=None)
    table.add_column("NAME")
    table.add_column("DEFAULT")
    if verbose:
        table.add_column("CREATED")

    sorted_pools = sorted(pools, key=lambda r: r.name)
    for pool in sorted_pools:
        row = [pool.name, "default" if pool.default else ""]
        if verbose:
            row.append(pretty_date(pool.created_at))
        table.add_row(*row)

    console.print(table)
    console.print()


def print_instance_table(instances: Sequence[Instance]):
    table = Table(box=None)
    table.add_column("INSTANCE ID")
    table.add_column("BACKEND")
    table.add_column("INSTANCE TYPE")
    table.add_column("PRICE")

    for instance in instances:
        row = [
            instance.instance_id,
            instance.backend,
            instance.instance_type.resources.pretty_format(),
            f"{instance.price:.02f}",
        ]
        table.add_row(*row)

    console.print(table)
    console.print()


def print_offers_table(
    pool_name: str,
    profile: Profile,
    requirements: Requirements,
    instance_offers: Sequence[InstanceOfferWithAvailability],
    offers_limit: int = 3,
):

    pretty_req = requirements.pretty_format(resources_only=True)
    max_price = f"${requirements.max_price:g}" if requirements.max_price else "-"
    max_duration = (
        f"{profile.max_duration / 3600:g}h" if isinstance(profile.max_duration, int) else "-"
    )

    # TODO: improve retry policy
    # retry_policy = profile.retry_policy
    # retry_policy = (
    #     (f"{retry_policy.limit / 3600:g}h" if retry_policy.limit else "yes")
    #     if retry_policy.retry
    #     else "no"
    # )

    # TODO: improve spot policy
    if requirements.spot is None:
        spot_policy = "auto"
    elif requirements.spot:
        spot_policy = "spot"
    else:
        spot_policy = "on-demand"

    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    props = Table(box=None, show_header=False)
    props.add_column(no_wrap=True)  # key
    props.add_column()  # value

    props.add_row(th("Pool name"), pool_name)
    props.add_row(th("Min resources"), pretty_req)
    props.add_row(th("Max price"), max_price)
    props.add_row(th("Max duration"), max_duration)
    props.add_row(th("Spot policy"), spot_policy)
    # props.add_row(th("Retry policy"), retry_policy)

    offers_table = Table(box=None)
    offers_table.add_column("#")
    offers_table.add_column("BACKEND")
    offers_table.add_column("REGION")
    offers_table.add_column("INSTANCE")
    offers_table.add_column("RESOURCES")
    offers_table.add_column("SPOT")
    offers_table.add_column("PRICE")
    offers_table.add_column()

    print_offers = instance_offers[:offers_limit]

    for i, offer in enumerate(print_offers, start=1):
        r = offer.instance.resources

        availability = ""
        if offer.availability in {
            InstanceAvailability.NOT_AVAILABLE,
            InstanceAvailability.NO_QUOTA,
        }:
            availability = offer.availability.value.replace("_", " ").title()
        offers_table.add_row(
            f"{i}",
            offer.backend,
            offer.region,
            offer.instance.name,
            r.pretty_format(),
            "yes" if r.spot else "no",
            f"${offer.price:g}",
            availability,
            style=None if i == 1 else "grey58",
        )
    if len(print_offers) > offers_limit:
        offers_table.add_row("", "...", style="grey58")

    console.print(props)
    console.print()
    if len(print_offers) > 0:
        console.print(offers_table)
        console.print()


class PoolCommand(APIBaseCommand):
    NAME = "pool"
    DESCRIPTION = "Pool management"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        # list
        list_parser = subparsers.add_parser(
            "list",
            help="List pools",
            description="List available pools",
            formatter_class=self._parser.formatter_class,
        )
        list_parser.add_argument("-v", "--verbose", help="Show more information")
        list_parser.set_defaults(subfunc=self._list)

        # create
        create_parser = subparsers.add_parser(
            "create", help="Create pool", formatter_class=self._parser.formatter_class
        )
        create_parser.add_argument("-n", "--name", dest="pool_name", help="The name of the pool")
        create_parser.set_defaults(subfunc=self._create)

        # delete
        delete_parser = subparsers.add_parser(
            "delete", help="Delete pool", formatter_class=self._parser.formatter_class
        )
        delete_parser.add_argument(
            "-n", "--name", dest="pool_name", help="The name of the pool", required=True
        )
        delete_parser.add_argument(
            "-f", "--force", dest="force", help="Force remove", type=bool, default=False
        )
        delete_parser.set_defaults(subfunc=self._delete)

        # show
        show_parser = subparsers.add_parser(
            "show",
            help="Show pool instances",
            description="Show instances in the pool",
            formatter_class=self._parser.formatter_class,
        )
        show_parser.add_argument(
            "-n", "--name", dest="pool_name", help="The name of the pool", required=True
        )
        show_parser.set_defaults(subfunc=self._show)

        # add
        add_parser = subparsers.add_parser(
            "add", help="Add instance to pool", formatter_class=self._parser.formatter_class
        )
        add_parser.add_argument(
            "--pool", dest="pool_name", help="The name of the pool", required=True
        )
        add_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        add_parser.set_defaults(subfunc=self._add)
        register_profile_args(add_parser)

    def _list(self, args: argparse.Namespace):
        pools = self.api.client.pool.list(self.api.project)
        print_pool_table(pools, verbose=getattr(args, "verbose", False))

    def _create(self, args: argparse.Namespace):
        self.api.client.pool.create(self.api.project, args.pool_name)

    def _delete(self, args: argparse.Namespace):
        self.api.client.pool.delete(self.api.project, args.pool_name, args.force)

    def _show(self, args: argparse.Namespace):
        instances = self.api.client.pool.show(self.api.project, args.pool_name)
        print_instance_table(instances)

    def _add(self, args: argparse.Namespace):
        super()._command(args)

        repo = self.api.repos.load(Path.cwd())
        self.api.ssh_identity_file = ConfigManager().get_repo_config(repo.repo_dir).ssh_key_path

        profile = load_profile(Path.cwd(), args.profile)
        apply_profile_args(args, profile)

        pool_name: str = DEFAULT_POOL_NAME if args.pool_name is None else args.pool_name
        profile.pool_name = pool_name

        with console.status("Getting run plan..."):
            requirements, offers = self.api.runs.get_offers(profile)

        print(pool_name, profile, requirements, offers)
        print_offers_table(pool_name, profile, requirements, offers)
        if not args.yes and not confirm_ask("Continue?"):
            console.print("\nExiting...")
            return

        try:
            with console.status("Submitting run..."):
                self.api.runs.create_instance(pool_name, profile)
        except ServerClientError as e:
            raise CLIError(e.msg)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        # TODO handle 404 and other errors
        args.subfunc(args)
