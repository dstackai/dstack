from typing import List

from rich.table import Table

from dstack._internal.cli.models.gateways import GatewayCommandOutput
from dstack._internal.cli.utils.common import (
    add_row_from_dict,
    console,
    format_backend,
    format_entity_reference,
)
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.common import EntityReference
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.utils.common import DateFormatter, interpolate_gateway_domain, pretty_date
from dstack.api.server._gateways import GatewaysAPIClient


def get_gateway_relative_to_project(
    client: GatewaysAPIClient, project: str, gateway_project: str, gateway_name: str
) -> Gateway:
    """
    Retrieves a single gateway, ensuring that `Gateway.default` is resolved relative to
    `project` rather than relative to the gateway's host project.
    """
    if project == gateway_project:
        return client.get(project, gateway_name)

    # For imported gateways, use `list`.
    # `get` would resolve `Gateway.default` relative to the gateway's host project
    gateways = client.list(project, include_imported=True)
    for gateway in gateways:
        if gateway.name == gateway_name and (
            gateway_project == gateway.project_name
            # Compatibility with pre-0.20.20 servers:
            # gateway.project_name is None means the gateway is in the current `project`
            or (gateway.project_name is None and gateway_project == project)
        ):
            return gateway
    ref = EntityReference(name=gateway_name, project=gateway_project)
    raise ResourceNotExistsError(msg=f"Gateway {ref.format()!r} not found in project {project!r}")


def print_gateways_table(gateways: List[Gateway], current_project: str, verbose: bool = False):
    table = get_gateways_table(gateways, current_project, verbose=verbose)
    console.print(table)
    console.print()


def print_gateways_json(gateways: List[Gateway], project: str) -> None:
    """Print gateways information in JSON format."""
    output = GatewayCommandOutput(
        project=project,
        gateways=gateways,
    )
    print(output.json())


def get_gateways_table(
    gateways: List[Gateway],
    current_project: str,
    verbose: bool = False,
    include_created: bool = False,
    format_date: DateFormatter = pretty_date,
) -> Table:
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("BACKEND")
    table.add_column("HOSTNAME", no_wrap=True)
    table.add_column("DOMAIN", no_wrap=True)
    table.add_column("DEFAULT")
    table.add_column("STATUS")
    if verbose or include_created:
        table.add_column("CREATED")
    if verbose:
        table.add_column("ERROR")

    for gateway in gateways:
        name = format_entity_reference(
            gateway.name,
            # project_name == None means pre-0.20.20 server, which means no gateway exports support,
            # which means the gateway is from the current project
            gateway.project_name if gateway.project_name is not None else current_project,
            current_project,
        )
        domain = gateway.wildcard_domain
        if (
            gateway.project_name is not None
            and gateway.project_name != current_project
            and domain is not None
        ):
            domain = interpolate_gateway_domain(
                domain=domain,
                run_project_name=current_project,
                # Ignore errors in case future server versions introduce more interpolation variables
                exception_type=None,
            )
        row = {
            "NAME": name,
            "BACKEND": format_backend(gateway.configuration.backend, gateway.configuration.region),
            "HOSTNAME": gateway.hostname,
            "DOMAIN": domain,
            "DEFAULT": "✓" if gateway.default else "",
            "STATUS": gateway.status,
            "CREATED": format_date(gateway.created_at),
            "ERROR": gateway.status_message,
        }
        add_row_from_dict(table, row)
    return table
