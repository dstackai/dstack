from pydantic import parse_obj_as

from dstack._internal.core.models.logs import JobSubmissionLogs
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack.api.server._group import APIClientGroup


class LogsAPIClient(APIClientGroup):
    def poll(self, project_name: str) -> JobSubmissionLogs:
        raise NotImplemented()
        body = PollLogsRequest()
        resp = self._request(f"/api/project/{project_name}/logs/poll", body=body.json())
        return parse_obj_as(JobSubmissionLogs, resp.json())
