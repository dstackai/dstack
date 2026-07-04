from typing import List, Optional

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


def print_endpoint(endpoint: Endpoint):
    console.print(get_endpoint_table(endpoint))
    console.print()


def get_endpoint_table(
    endpoint: Endpoint,
    format_date: DateFormatter = pretty_date,
) -> Table:
    table = Table(box=None, show_header=False)
    table.add_column(no_wrap=True)
    table.add_column()

    def th(value: str) -> str:
        return f"[bold]{value}[/bold]"

    table.add_row(th("Project"), endpoint.project_name)
    table.add_row(th("User"), endpoint.user)
    table.add_row(th("Endpoint"), endpoint.name)
    table.add_row(th("Model"), endpoint.configuration.model)
    table.add_row(th("Status"), _format_endpoint_status(endpoint.status, endpoint.status_message))
    table.add_row(th("Run"), endpoint.run_name or "-")
    table.add_row(th("URL"), endpoint.url or "-")
    table.add_row(th("Created"), format_date(endpoint.created_at))
    if endpoint.status_message:
        table.add_row(th("Error"), endpoint.status_message)
    return table


def get_endpoints_table(
    endpoints: List[Endpoint],
    verbose: bool = False,
    format_date: DateFormatter = pretty_date,
) -> Table:
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("MODEL")
    table.add_column("STATUS", no_wrap=True)
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
            "STATUS": _format_endpoint_status(endpoint.status, endpoint.status_message),
            "RUN": endpoint.run_name or "-",
            "URL": endpoint.url or "-",
            "CREATED": format_date(endpoint.created_at),
            "ERROR": endpoint.status_message,
        }
        add_row_from_dict(table, row)
    return table


def _format_endpoint_status(
    status: EndpointStatus,
    status_message: Optional[str] = None,
) -> str:
    status_value = _get_endpoint_status_value(status, status_message)
    color_map = {
        EndpointStatus.SUBMITTED: "grey",
        EndpointStatus.PROVISIONING: "deep_sky_blue1",
        EndpointStatus.AGENTING: "medium_purple1",
        EndpointStatus.RUNNING: "sea_green3",
        EndpointStatus.ACTIVE: "sea_green3",
        EndpointStatus.FAILED: "indian_red1",
    }
    if status_value == "no offers":
        style = "gold1"
    else:
        style = color_map.get(status, "white")
    if not status.is_finished():
        style = f"bold {style}"
    return f"[{style}]{status_value}[/]"


def _get_endpoint_status_value(
    status: EndpointStatus,
    status_message: Optional[str],
) -> str:
    if status == EndpointStatus.ACTIVE:
        return EndpointStatus.RUNNING.value
    if status == EndpointStatus.FAILED:
        failure_reason = _get_endpoint_failure_reason(status_message)
        if failure_reason is not None:
            return failure_reason
    return status.value


def _get_endpoint_failure_reason(status_message: Optional[str]) -> Optional[str]:
    if status_message is None:
        return None
    normalized = " ".join(status_message.lower().split())
    if not normalized:
        return None
    if any(
        phrase in normalized
        for phrase in [
            "no matching instance offers",
            "no matching offers",
            "no offers",
            "no-offer",
            "zero offers",
            "total_offers: 0",
        ]
    ):
        return "no offers"
    if "no fleets" in normalized:
        return "no fleets"
    if (
        "requires the server agent" in normalized
        or "server agent runtime" in normalized
        or "dstack_agent_" in normalized
        or "claude executable" in normalized
    ):
        return "no agent"
    if "no matching endpoint presets" in normalized:
        return "no preset"
    if "server agent" in normalized or "agent" in normalized:
        return "agent failed"
    if "run name" in normalized and "taken" in normalized:
        return "conflict"
    if "backing service run" in normalized:
        return "run failed"
    return None
