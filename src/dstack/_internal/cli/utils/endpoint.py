from typing import List

from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.endpoints import Endpoint, EndpointStatus
from dstack._internal.utils.common import DateFormatter, pretty_date


def filter_endpoints_for_listing(
    endpoints: List[Endpoint],
    show_all: bool = False,
    limit: int | None = None,
    include_latest_finished: bool = True,
) -> List[Endpoint]:
    endpoints = sorted(
        endpoints,
        key=lambda endpoint: (endpoint.created_at, str(endpoint.id)),
        reverse=True,
    )
    if limit is not None:
        return endpoints[:limit]
    if show_all:
        return endpoints

    latest_finished = None
    filtered = []
    for endpoint in endpoints:
        if endpoint.status.is_finished():
            if not include_latest_finished:
                continue
            if latest_finished is None:
                latest_finished = endpoint
                filtered.append(endpoint)
            continue
        filtered.append(endpoint)
    return filtered


def print_endpoints_table(endpoints: List[Endpoint], verbose: bool = False):
    table = get_endpoints_table(endpoints, verbose=verbose)
    console.print(table)
    console.print()


def get_endpoints_table(
    endpoints: List[Endpoint],
    verbose: bool = False,
    format_date: DateFormatter = pretty_date,
) -> Table:
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("MODEL")
    table.add_column("STATUS")
    table.add_column("RUN")
    if verbose:
        table.add_column("URL")
    table.add_column("CREATED")
    if verbose:
        table.add_column("ERROR")

    for endpoint in endpoints:
        row = {
            "NAME": endpoint.name,
            "MODEL": endpoint.configuration.model,
            "STATUS": _format_endpoint_status(endpoint.status),
            "RUN": endpoint.run_name or "-",
            "URL": endpoint.url or "-",
            "CREATED": format_date(endpoint.created_at),
            "ERROR": endpoint.status_message,
        }
        add_row_from_dict(table, row)
    return table


def _format_endpoint_status(status: EndpointStatus) -> str:
    color_map = {
        EndpointStatus.SUBMITTED: "grey",
        EndpointStatus.PROVISIONING: "deep_sky_blue1",
        EndpointStatus.AGENTING: "medium_purple1",
        EndpointStatus.RUNNING: "sea_green3",
        EndpointStatus.ACTIVE: "sea_green3",
        EndpointStatus.FAILED: "indian_red1",
    }
    style = color_map.get(status, "white")
    if not status.is_finished():
        style = f"bold {style}"
    status_value = (
        EndpointStatus.RUNNING.value if status == EndpointStatus.ACTIVE else status.value
    )
    return f"[{style}]{status_value}[/]"
