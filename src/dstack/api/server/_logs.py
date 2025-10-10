from pydantic import parse_obj_as

from dstack._internal.core.compatibility.logs import get_poll_logs_excludes
from dstack._internal.core.models.logs import JobSubmissionLogs
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack.api.server._group import APIClientGroup


class LogsAPIClient(APIClientGroup):
    def poll(self, project_name: str, body: PollLogsRequest) -> JobSubmissionLogs:
        resp = self._request(
            f"/api/project/{project_name}/logs/poll",
            body=body.json(exclude=get_poll_logs_excludes(body)),
        )
        return parse_obj_as(JobSubmissionLogs.__response__, resp.json())
