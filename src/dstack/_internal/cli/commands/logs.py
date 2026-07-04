import argparse
import base64
import sys
from typing import Iterable

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import RunOrEndpointNameCompleter
from dstack._internal.cli.utils.common import get_start_time
from dstack._internal.core.errors import CLIError, ResourceNotExistsError
from dstack._internal.core.models.endpoints import Endpoint
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class LogsCommand(APIBaseCommand):
    NAME = "logs"
    DESCRIPTION = "Show logs"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "-d", "--diagnose", action="store_true", help="Show run diagnostic logs"
        )
        self._parser.add_argument(
            "--replica",
            help="The replica number. Defaults to 0.",
            type=int,
            default=0,
        )
        self._parser.add_argument(
            "--job",
            help="The job number inside the replica. Defaults to 0.",
            type=int,
            default=0,
        )
        self._parser.add_argument(
            "--since",
            help=(
                "Show only logs newer than the specified date."
                " Can be a duration (e.g. 10s, 5m, 1d) or an RFC 3339 string (e.g. 2023-09-24T15:30:00Z)."
            ),
            type=str,
        )
        self._parser.add_argument("run_name").completer = RunOrEndpointNameCompleter()  # type: ignore[attr-defined]

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        start_time = get_start_time(args.since)
        logs = self._get_logs(args=args, start_time=start_time)
        try:
            for log in logs:
                sys.stdout.buffer.write(log)
                sys.stdout.buffer.flush()
        except KeyboardInterrupt:
            pass

    def _get_logs(
        self,
        args: argparse.Namespace,
        start_time,
    ) -> Iterable[bytes]:
        endpoint = self._get_endpoint(args.run_name)
        if endpoint is not None:
            return self._get_endpoint_logs(endpoint=endpoint, args=args, start_time=start_time)

        run = self.api.runs.get(args.run_name)
        if run is not None:
            return run.logs(
                start_time=start_time,
                diagnose=args.diagnose,
                replica_num=args.replica,
                job_num=args.job,
            )

        raise CLIError(f"Run or endpoint {args.run_name} not found")

    def _get_endpoint(self, name: str) -> Endpoint | None:
        try:
            return self.api.client.endpoints.get(
                project_name=self.api.project,
                name=name,
            )
        except ResourceNotExistsError:
            return None

    def _get_endpoint_logs(
        self,
        endpoint: Endpoint,
        args: argparse.Namespace,
        start_time,
    ) -> Iterable[bytes]:
        if endpoint.run_name is not None:
            run = self.api.runs.get(endpoint.run_name)
            if run is not None:
                yield from run.logs(
                    start_time=start_time,
                    diagnose=args.diagnose,
                    replica_num=args.replica,
                    job_num=args.job,
                )
                return

        next_token = None
        while True:
            resp = self.api.client.logs.poll(
                project_name=self.api.project,
                body=PollLogsRequest(
                    run_name=endpoint.name,
                    job_submission_id=endpoint.id,
                    start_time=start_time,
                    end_time=None,
                    descending=False,
                    limit=1000,
                    diagnose=False,
                    next_token=next_token,
                ),
            )
            for log in resp.logs:
                yield base64.b64decode(log.message)
            next_token = resp.next_token
            if next_token is None:
                break
