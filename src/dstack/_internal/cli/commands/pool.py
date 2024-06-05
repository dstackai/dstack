import argparse
import getpass
import ipaddress
import time
import urllib.parse
from pathlib import Path
from typing import Optional, Sequence, Tuple

from rich.console import Group
from rich.live import Live
from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.args import cpu_spec, disk_spec, gpu_spec, memory_spec
from dstack._internal.cli.services.profile import (
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
from dstack._internal.core.models.profiles import Profile, SpotPolicy, parse_duration
from dstack._internal.core.models.resources import DEFAULT_CPU_COUNT, DEFAULT_MEMORY_SIZE
from dstack._internal.core.models.runs import InstanceStatus, Requirements, get_policy_map
from dstack._internal.utils.common import pretty_date
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import convert_pkcs8_to_pem, generate_public_key, rsa_pkey_from_str
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
        # TODO: support --force
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
        self._parser.add_argument(
            "--max-offers",
            help="Number of offers to show in the run plan",
            type=int,
            default=3,
        )
        add_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        register_profile_args(add_parser, pool_add=True)
        register_resource_args(add_parser)
        add_parser.set_defaults(subfunc=self._add)

        # remove instance
        remove_parser = subparsers.add_parser(
            "rm",
            help="Remove instance from the pool",
            formatter_class=self._parser.formatter_class,
            aliases=["remove"],
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

        # add-ssh
        add_ssh = subparsers.add_parser(
            "add-ssh",
            help="Add remote instance to pool",
            formatter_class=self._parser.formatter_class,
        )
        add_ssh.add_argument("destination")
        add_ssh.add_argument(
            "-i",
            metavar="SSH_PRIVATE_KEY",
            help="The private SSH key path for SSH",
            type=Path,
            dest="ssh_identity_file",
            required=True,
        )
        add_ssh.add_argument("-p", help="SSH port to connect", dest="ssh_port", type=int)
        add_ssh.add_argument("-l", help="User to login", dest="login_name")
        add_ssh.add_argument("--region", help="Host region", dest="region")
        add_ssh.add_argument("--pool", help="Pool name", dest="pool_name")
        add_ssh.add_argument("--name", dest="instance_name", help="Set the name of the instance")
        add_ssh.add_argument(
            "--network",
            dest="network",
            help="Network address for multinode setup. Format <ip address>/<netmask>",
        )
        add_ssh.set_defaults(subfunc=self._add_ssh)

    def _list(self, args: argparse.Namespace) -> None:
        pools = self.api.client.pool.list(self.api.project)
        print_pool_table(pools, verbose=getattr(args, "verbose", False))

    def _create(self, args: argparse.Namespace) -> None:
        self.api.client.pool.create(self.api.project, args.pool_name)
        console.print(f"Pool {args.pool_name!r} created")

    def _delete(self, args: argparse.Namespace) -> None:
        # TODO(egor-s): ask for confirmation
        with console.status("Removing pool..."):
            self.api.client.pool.delete(self.api.project, args.pool_name, False)
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
        self.api.client.pool.set_default(self.api.project, args.pool_name)

    def _ps(self, args: argparse.Namespace) -> None:
        pool_name_template = " [bold]Pool name[/]  {}\n"
        if not args.watch:
            resp = self.api.client.pool.show(self.api.project, args.pool_name)
            console.print(pool_name_template.format(resp.name))
            print_instance_table(resp.instances)
            return

        try:
            with Live(console=console, refresh_per_second=REFRESH_RATE_PER_SEC) as live:
                while True:
                    resp = self.api.client.pool.show(self.api.project, args.pool_name)
                    group = Group(
                        pool_name_template.format(resp.name), get_instance_table(resp.instances)
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

        profile = load_profile(Path.cwd(), args.profile)
        apply_profile_args(args, profile, pool_add=True)

        spot = get_policy_map(profile.spot_policy, default=SpotPolicy.ONDEMAND)

        requirements = Requirements(
            resources=resources,
            max_price=profile.max_price,
            spot=spot,
        )

        with console.status("Getting instances..."):
            pool_offers = self.api.runs.get_offers(profile, requirements)

        profile.pool_name = pool_offers.pool_name

        print_offers_table(
            profile=profile,
            requirements=requirements,
            instance_offers=pool_offers.instances,
            offers_limit=args.max_offers,
        )
        if not pool_offers.instances:
            console.print("\nThere are no offers with these criteria. Exiting...")
            return

        if not args.yes and not confirm_ask("Continue?"):
            console.print("\nExiting...")
            return

        try:
            with console.status("Creating instance..."):
                # TODO: Instance name is not passed, so --instance does not work.
                # There is profile.instance_name but it makes sense for `dstack run` only.
                instance = self.api.runs.create_instance(profile, requirements)
        except ServerClientError as e:
            raise CLIError(e.msg)
        console.print()
        print_instance_table([instance])

    def _add_ssh(self, args: argparse.Namespace) -> None:
        super()._command(args)

        # validate network
        if args.network is not None:
            try:
                network = ipaddress.IPv4Interface(args.network).network
            except ValueError as e:
                console.print(
                    f"[error]Can't parse network. The address must be in the format <network address>/<netmask>, example `10.0.0.0/24`. Error: {e}[/]"
                )
                return
            if not network.is_private:
                console.print(
                    f"[error]The network must be private network. The {network} is not private[/]"
                )
                return

        ssh_keys = []
        if args.ssh_identity_file:
            try:
                private_key = convert_pkcs8_to_pem(args.ssh_identity_file.read_text())
                try:
                    pub_key = args.ssh_identity_file.with_suffix(".pub").read_text()
                except FileNotFoundError:
                    pub_key = generate_public_key(rsa_pkey_from_str(private_key))
                ssh_key = SSHKey(public=pub_key, private=private_key)
                ssh_keys.append(ssh_key)
            except OSError:
                console.print("[error]Unable to read the public key.[/]")
                return

        login, ssh_host, port = parse_destination(args.destination)

        ssh_port = 22
        if port is not None:
            ssh_port = port
        if args.ssh_port is not None:
            ssh_port = args.ssh_port

        ssh_user = args.login_name
        if ssh_user is None:
            ssh_user = login
        if ssh_user is None:
            try:
                ssh_user = getpass.getuser()
            except OSError:
                console.print("[error]Set the user name with the `-l` parameter.[/]")
                return

        result = self.api.client.pool.add_remote(
            project_name=self.api.project,
            pool_name=args.pool_name,
            instance_name=args.instance_name,
            instance_network=args.network,
            region=args.region,
            host=ssh_host,
            port=ssh_port,
            ssh_user=ssh_user,
            ssh_keys=ssh_keys,
        )
        if not result:
            console.print(f"[error]Failed to add remote instance {args.instance_name!r}[/]")
            return
        console.print(
            f"Remote instance [code]{result.name!r}[/] has been added with status [secondary]{result.status.upper()}[/]"
        )

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


def print_instance_table(instances: Sequence[Instance]) -> None:
    console.print(get_instance_table(instances))
    console.print()


def get_instance_table(instances: Sequence[Instance]) -> Table:
    table = Table(box=None)
    table.add_column("INSTANCE", no_wrap=True)
    table.add_column("BACKEND")
    table.add_column("REGION")
    table.add_column("RESOURCES")
    table.add_column("SPOT")
    table.add_column("PRICE")
    table.add_column("STATUS")
    table.add_column("CREATED")

    for instance in instances:
        resources = ""
        spot = ""
        if instance.instance_type is not None:
            resources = instance.instance_type.resources.pretty_format()
            spot = "yes" if instance.instance_type.resources.spot else "no"

        status = instance.status.value
        if instance.status in [InstanceStatus.IDLE, InstanceStatus.BUSY] and instance.unreachable:
            status += "\n(unreachable)"

        row = [
            instance.name,
            (instance.backend or "").replace("remote", "ssh"),
            instance.region or "",
            resources,
            spot,
            f"${instance.price:.4}" if instance.price is not None else "",
            status,
            pretty_date(instance.created),
        ]
        table.add_row(*row)

    return table


def print_offers_table(
    profile: Profile,
    requirements: Requirements,
    instance_offers: Sequence[InstanceOfferWithAvailability],
    offers_limit: int,
) -> None:
    pretty_req = requirements.pretty_format(resources_only=True)
    max_price = f"${requirements.max_price:g}" if requirements.max_price else "-"
    termination_policy = profile.termination_policy
    termination_idle_time = f"{parse_duration(profile.termination_idle_time)}s"

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

    props.add_row(th("Pool"), profile.pool_name)
    props.add_row(th("Min resources"), pretty_req)
    props.add_row(th("Max price"), max_price)
    props.add_row(th("Spot policy"), spot_policy)
    props.add_row(th("Termination policy"), termination_policy)
    props.add_row(th("Termination idle time"), termination_idle_time)

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

    for index, offer in enumerate(print_offers, start=1):
        resources = offer.instance.resources

        availability = ""
        if offer.availability in {
            InstanceAvailability.NOT_AVAILABLE,
            InstanceAvailability.NO_QUOTA,
        }:
            availability = offer.availability.value.replace("_", " ").title()
        offers_table.add_row(
            f"{index}",
            offer.backend.replace("remote", "ssh"),
            offer.region,
            offer.instance.name,
            resources.pretty_format(),
            "yes" if resources.spot else "no",
            f"${offer.price:g}",
            availability,
            style=None if index == 1 else "secondary",
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


def parse_destination(destination: str) -> Tuple[Optional[str], str, Optional[int]]:
    port = None
    netloc = destination

    if destination.startswith("ssh://"):
        parse_result = urllib.parse.urlparse(destination)
        netloc, _, netloc_port = parse_result.netloc.partition(":")
        try:
            port = int(netloc_port)
        except ValueError:
            pass

    head, sep, tail = netloc.partition("@")
    if sep == "@":
        login = head
        host = tail
    else:
        login = None
        host = head
    return login, host, port
