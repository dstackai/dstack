import argparse
import datetime
import time
from pathlib import Path
from typing import Sequence

from rich.console import Group
from rich.live import Live
from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.args import cpu_spec, disk_spec, gpu_spec, memory_spec
from dstack._internal.cli.services.configurators.profile import (
    apply_profile_args,
    register_profile_args,
)
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.core.errors import CLIError, ServerClientError
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    SSHKey,
)
from dstack._internal.core.models.pools import Instance, Pool
from dstack._internal.core.models.profiles import (
    DEFAULT_TERMINATION_IDLE_TIME,
    Profile,
    SpotPolicy,
    TerminationPolicy,
)
from dstack._internal.core.models.resources import DEFAULT_CPU_COUNT, DEFAULT_MEMORY_SIZE
from dstack._internal.core.models.runs import InstanceStatus, Requirements
from dstack._internal.utils.common import pretty_date
from dstack._internal.utils.logging import get_logger
from dstack.api._public.resources import Resources
from dstack.api.utils import load_profile

REFRESH_RATE_PER_SEC = 5
LIVE_PROVISION_INTERVAL_SECS = 10

logger = get_logger(__name__)


class PoolCommand(APIBaseCommand):
    NAME = "pool"
    DESCRIPTION = "Pool management"

    def _register(self) -> None:
        super()._register()
        self._parser.set_defaults(subfunc=self._list)

        subparsers = self._parser.add_subparsers(dest="action")

        # list pools
        list_parser = subparsers.add_parser(
            "list",
            help="List pools",
            description="List available pools",
            formatter_class=self._parser.formatter_class,
        )
        list_parser.add_argument("-v", "--verbose", help="Show more information")
        list_parser.set_defaults(subfunc=self._list)

        # create pool
        create_parser = subparsers.add_parser(
            "create", help="Create pool", formatter_class=self._parser.formatter_class
        )
        create_parser.add_argument(
            "-n", "--name", dest="pool_name", help="The name of the pool", required=True
        )
        create_parser.set_defaults(subfunc=self._create)

        # delete pool
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

        # show pool instances
        ps_parser = subparsers.add_parser(
            "ps",
            help="Show pool instances",
            description="Show instances in the pool",
            formatter_class=self._parser.formatter_class,
        )
        ps_parser.add_argument(
            "--pool",
            dest="pool_name",
            help="The name of the pool. If not set, the default pool will be used",
        )
        ps_parser.add_argument(
            "-w",
            "--watch",
            help="Watch instances in realtime",
            action="store_true",
        )
        ps_parser.set_defaults(subfunc=self._ps)

        # add instance
        add_parser = subparsers.add_parser(
            "add", help="Add instance to pool", formatter_class=self._parser.formatter_class
        )
        add_parser.add_argument(
            "--pool",
            dest="pool_name",
            help="The name of the pool. If not set, the default pool will be used",
        )
        add_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        add_parser.add_argument(
            "--remote",
            help="Add remote runner as an instance",
            dest="remote",
            action="store_true",
            default=False,
        )
        add_parser.add_argument("--remote-host", help="Remote runner host", dest="remote_host")
        add_parser.add_argument(
            "--remote-port", help="Remote runner port", dest="remote_port", default=10999
        )
        add_parser.add_argument("--name", dest="instance_name", help="The name of the instance")
        register_profile_args(add_parser)
        register_resource_args(add_parser)
        add_parser.set_defaults(subfunc=self._add)

        # remove instance
        remove_parser = subparsers.add_parser(
            "remove",
            help="Remove instance from the pool",
            formatter_class=self._parser.formatter_class,
        )
        remove_parser.add_argument(
            "instance_name",
            help="The name of the instance",
        )
        remove_parser.add_argument(
            "--pool",
            dest="pool_name",
            help="The name of the pool. If not set, the default pool will be used",
        )
        remove_parser.add_argument(
            "--force",
            action="store_true",
            help="The name of the instance",
        )
        remove_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        remove_parser.set_defaults(subfunc=self._remove)

        # pool set-default
        set_default_parser = subparsers.add_parser(
            "set-default",
            help="Set the project's default pool",
            formatter_class=self._parser.formatter_class,
        )
        set_default_parser.add_argument(
            "--pool", dest="pool_name", help="The name of the pool", required=True
        )
        set_default_parser.set_defaults(subfunc=self._set_default)

    def _list(self, args: argparse.Namespace) -> None:
        pools = self.api.client.pool.list(self.api.project)
        print_pool_table(pools, verbose=getattr(args, "verbose", False))

    def _create(self, args: argparse.Namespace) -> None:
        self.api.client.pool.create(self.api.project, args.pool_name)
        console.print(f"Pool {args.pool_name!r} created")

    def _delete(self, args: argparse.Namespace) -> None:
        # TODO(egor-s): ask for confirmation
        with console.status("Removing pool..."):
            self.api.client.pool.delete(self.api.project, args.pool_name, args.force)
        console.print(f"Pool {args.pool_name!r} removed")

    def _remove(self, args: argparse.Namespace) -> None:
        pool = self.api.client.pool.show(self.api.project, args.pool_name)
        pool.instances = [i for i in pool.instances if i.name == args.instance_name]
        if not pool.instances:
            raise CLIError(f"Instance {args.instance_name!r} not found in pool {pool.name!r}")

        console.print(f" [bold]Pool name[/]  {pool.name}\n")
        print_instance_table(pool.instances)

        if not args.force and any(i.status == InstanceStatus.BUSY for i in pool.instances):
            # TODO(egor-s): implement this logic in the server too
            raise CLIError("Can't remove busy instance. Use `--force` to remove anyway")

        if not args.yes and not confirm_ask(f"Remove instance {args.instance_name!r}?"):
            console.print("\nExiting...")
            return

        with console.status("Removing instance..."):
            self.api.client.pool.remove(
                self.api.project, pool.name, args.instance_name, args.force
            )
        console.print(f"Instance {args.instance_name!r} removed")

    def _set_default(self, args: argparse.Namespace) -> None:
        result = self.api.client.pool.set_default(self.api.project, args.pool_name)
        if not result:
            console.print(f"Failed to set default pool {args.pool_name!r}", style="error")

    def _ps(self, args: argparse.Namespace) -> None:
        pool_name_template = " [bold]Pool name[/]  {}\n"
        if not args.watch:
            resp = self.api.client.pool.show(self.api.project, args.pool_name)
            console.print(pool_name_template.format(resp.name))
            console.print(print_instance_table(resp.instances))
            console.print()
            return

        try:
            with Live(console=console, refresh_per_second=REFRESH_RATE_PER_SEC) as live:
                while True:
                    resp = self.api.client.pool.show(self.api.project, args.pool_name)
                    group = Group(
                        pool_name_template.format(resp.name), print_instance_table(resp.instances)
                    )
                    live.update(group)
                    time.sleep(LIVE_PROVISION_INTERVAL_SECS)
        except KeyboardInterrupt:
            pass

    def _add(self, args: argparse.Namespace) -> None:
        super()._command(args)

        resources = Resources(
            cpu=args.cpu,
            memory=args.memory,
            gpu=args.gpu,
            shm_size=args.shared_memory,
            disk=args.disk,
        )
        requirements = Requirements(
            resources=resources,
            max_price=args.max_price,
            spot=(args.spot_policy == SpotPolicy.SPOT),  # TODO(egor-s): None if SpotPolicy.AUTO
        )

        profile = load_profile(Path.cwd(), args.profile)
        apply_profile_args(args, profile)
        profile.pool_name = args.pool_name

        termination_policy_idle = DEFAULT_TERMINATION_IDLE_TIME
        termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
        profile.termination_idle_time = termination_policy_idle
        profile.termination_policy = termination_policy

        # Add remote instance
        if args.remote:
            result = self.api.client.pool.add_remote(
                self.api.project,
                resources,
                profile,
                args.instance_name,
                args.remote_host,
                args.remote_port,
            )
            if not result:
                console.print(f"[error]Failed to add remote instance {args.instance_name!r}[/]")
            # TODO(egor-s): print on success
            return

        with console.status("Getting instances..."):
            pool_name, offers = self.api.runs.get_offers(profile, requirements)

        print_offers_table(pool_name, profile, requirements, offers)
        if not args.yes and not confirm_ask("Continue?"):
            console.print("\nExiting...")
            return

        # TODO(egor-s): user pub key must be added during the `run`, not `pool add`
        user_pub_key = Path("~/.dstack/ssh/id_rsa.pub").expanduser().read_text().strip()
        pub_key = SSHKey(public=user_pub_key)
        try:
            with console.status("Creating instance..."):
                instance = self.api.runs.create_instance(pool_name, profile, requirements, pub_key)
        except ServerClientError as e:
            raise CLIError(e.msg)
        print_instance_table([instance])

    def _command(self, args: argparse.Namespace) -> None:
        super()._command(args)
        # TODO handle 404 and other errors
        args.subfunc(args)


def print_pool_table(pools: Sequence[Pool], verbose: bool) -> None:
    table = Table(box=None)
    table.add_column("NAME")
    table.add_column("DEFAULT")
    table.add_column("INSTANCES")
    if verbose:
        table.add_column("CREATED")

    sorted_pools = sorted(pools, key=lambda r: r.name)
    for pool in sorted_pools:
        default_mark = "default" if pool.default else ""
        style = "success" if pool.total_instances == pool.available_instances else "error"
        health = f"[{style}]{pool.available_instances}/{pool.total_instances}[/]"
        row = [pool.name, default_mark, health]
        if verbose:
            row.append(pretty_date(pool.created_at))
        table.add_row(*row)

    console.print(table)
    console.print()


def print_instance_table(instances: Sequence[Instance]) -> Table:
    table = Table(box=None)
    table.add_column("INSTANCE")
    table.add_column("BACKEND")
    table.add_column("REGION")
    table.add_column("RESOURCES")
    table.add_column("SPOT")
    table.add_column("STATUS")
    table.add_column("PRICE")
    table.add_column("CREATED")

    for instance in instances:
        style = "success" if instance.status.is_available() else "warning"
        created = (
            pretty_date(instance.created.replace(tzinfo=datetime.timezone.utc))
            if instance.created is not None
            else ""
        )
        row = [
            instance.name,
            instance.backend,
            instance.region,
            instance.instance_type.resources.pretty_format(),
            "yes" if instance.instance_type.resources.spot else "no",
            f"[{style}]{instance.status.value}[/]",
            f"${instance.price:.4}",
            created,
        ]
        table.add_row(*row)

    return table


def print_offers_table(
    pool_name: str,
    profile: Profile,
    requirements: Requirements,
    instance_offers: Sequence[InstanceOfferWithAvailability],
    offers_limit: int = 3,
) -> None:
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
            style=None if i == 1 else "secondary",
        )
    if len(print_offers) > offers_limit:
        offers_table.add_row("", "...", style="secondary")

    console.print(props)
    console.print()
    if len(print_offers) > 0:
        console.print(offers_table)
        console.print()


def register_resource_args(parser: argparse.ArgumentParser) -> None:
    resources_group = parser.add_argument_group("Resources")
    resources_group.add_argument(
        "--cpu",
        help=f"Request the CPU count. Default: {DEFAULT_CPU_COUNT}",
        dest="cpu",
        metavar="SPEC",
        default=DEFAULT_CPU_COUNT,
        type=cpu_spec,
    )

    resources_group.add_argument(
        "--memory",
        help="Request the size of RAM. "
        f"The format is [code]SIZE[/]:[code]MB|GB|TB[/]. Default: {DEFAULT_MEMORY_SIZE}",
        dest="memory",
        metavar="SIZE",
        default=DEFAULT_MEMORY_SIZE,
        type=memory_spec,
    )

    resources_group.add_argument(
        "--shared-memory",
        help="Request the size of Shared Memory. The format is [code]SIZE[/]:[code]MB|GB|TB[/].",
        dest="shared_memory",
        default=None,
        metavar="SIZE",
    )

    resources_group.add_argument(
        "--gpu",
        help="Request GPU for the run. "
        "The format is [code]NAME[/]:[code]COUNT[/]:[code]MEMORY[/] (all parts are optional)",
        dest="gpu",
        default=None,
        metavar="SPEC",
        type=gpu_spec,
    )

    resources_group.add_argument(
        "--disk",
        help="Request the size of disk for the run. Example [code]--disk 100GB..[/].",
        dest="disk",
        metavar="SIZE",
        default=None,
        type=disk_spec,
    )
