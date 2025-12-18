import argparse
from dataclasses import asdict

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.events import EventListFilters, EventPaginator, print_event
from dstack._internal.cli.utils.common import (
    get_start_time,
)
from dstack._internal.core.models.events import EventTargetType
from dstack._internal.server.schemas.events import LIST_EVENTS_DEFAULT_LIMIT
from dstack.api import Client


class EventCommand(APIBaseCommand):
    NAME = "event"
    DESCRIPTION = "View events"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list",
            help="List events within the selected project",
            formatter_class=self._parser.formatter_class,
        )
        list_parser.set_defaults(subfunc=self._list)

        for parser in [self._parser, list_parser]:
            parser.add_argument(
                "--since",
                help=(
                    "Only show events newer than the specified date."
                    " Can be a duration (e.g. 10s, 5m, 1d) or an RFC 3339 string (e.g. 2023-09-24T15:30:00Z)."
                    f" If not specified, show the last {LIST_EVENTS_DEFAULT_LIMIT} events."
                ),
                type=str,
            )
            target_filters_group = parser.add_mutually_exclusive_group()
            target_filters_group.add_argument(
                "--target-fleet",
                action="append",
                metavar="NAME",
                dest="target_fleets",
                help="Only show events that target the specified fleets",
            )
            target_filters_group.add_argument(
                "--target-run",
                action="append",
                metavar="NAME",
                dest="target_runs",
                help="Only show events that target the specified runs",
            )
            within_filters_group = parser.add_mutually_exclusive_group()
            within_filters_group.add_argument(
                "--within-fleet",
                action="append",
                metavar="NAME",
                dest="within_fleets",
                help="Only show events that target the specified fleets or instances within those fleets",
            )
            within_filters_group.add_argument(
                "--within-run",
                action="append",
                metavar="NAME",
                dest="within_runs",
                help="Only show events that target the specified runs or jobs within those runs",
            )
            parser.add_argument(
                "--include-target-type",
                action="append",
                metavar="TYPE",
                type=EventTargetType,
                dest="include_target_types",
                help="Only show events that target entities of the specified types",
            )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        since = get_start_time(args.since)
        filters = _build_filters(args, self.api)

        if since is not None:
            events = EventPaginator(self.api.client.events).list(
                filters=filters, since=since, ascending=True
            )
        else:
            events = reversed(self.api.client.events.list(ascending=False, **asdict(filters)))
        try:
            for event in events:
                print_event(event)
        except KeyboardInterrupt:
            pass


def _build_filters(args: argparse.Namespace, api: Client) -> EventListFilters:
    filters = EventListFilters()

    if args.target_fleets:
        filters.target_fleets = [
            api.client.fleets.get(api.project, name).id for name in args.target_fleets
        ]
    elif args.target_runs:
        filters.target_runs = [
            api.client.runs.get(api.project, name).id for name in args.target_runs
        ]

    if args.within_fleets:
        filters.within_fleets = [
            api.client.fleets.get(api.project, name).id for name in args.within_fleets
        ]
    elif args.within_runs:
        filters.within_runs = [
            api.client.runs.get(api.project, name).id for name in args.within_runs
        ]
    else:
        filters.within_projects = [api.client.projects.get(api.project).project_id]

    if args.include_target_types:
        filters.include_target_types = args.include_target_types

    return filters
