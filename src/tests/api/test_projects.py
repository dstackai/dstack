import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from dstack.api.server._projects import ProjectsAPIClient
from tests.api.common import RequestRecorder

PROJECT_PAYLOAD = {
    "project_id": "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
    "project_name": "p",
    "owner": {
        "id": "2b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
        "username": "u",
        "created_at": "2023-01-02T03:04:00+00:00",
        "global_role": "user",
        "email": None,
        "active": True,
        "permissions": {"can_create_projects": True},
        "ssh_public_key": None,
    },
    "created_at": "2023-01-02T03:04:00+00:00",
    "backends": [],
    "members": [],
    "is_public": False,
}


class TestProjectsAPIClientList:
    def test_projects_list_serializes_pagination_and_parses_info_list(self):
        request = RequestRecorder(payload={"total_count": 1, "projects": [PROJECT_PAYLOAD]})
        client = ProjectsAPIClient(_request=request, _logger=logging.getLogger("test"))
        dt = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        pid = UUID("3b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")

        result = client.list(
            return_total_count=True,
            prev_created_at=dt,
            name_pattern="p",
            prev_id=pid,
            limit=1,
            ascending=True,
        )

        payload = json.loads(request.last_body)
        assert request.last_path == "/api/projects/list"
        assert payload["include_not_joined"] is True
        assert payload["return_total_count"] is True
        assert payload["name_pattern"] == "p"
        assert payload["prev_created_at"] == dt.isoformat()
        assert payload["prev_id"] == str(pid)
        assert payload["limit"] == 1
        assert payload["ascending"] is True
        assert result.total_count == 1
        assert result.projects[0].project_name == "p"

    def test_projects_list_parses_list_response(self):
        request = RequestRecorder(payload=[PROJECT_PAYLOAD])
        client = ProjectsAPIClient(_request=request, _logger=logging.getLogger("test"))
        result = client.list()
        assert isinstance(result, list)
        assert result[0].project_name == PROJECT_PAYLOAD["project_name"]
