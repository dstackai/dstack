import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from dstack.api.server._users import UsersAPIClient
from tests.api.common import RequestRecorder

USER_PAYLOAD = {
    "id": "11111111-1111-4111-8111-111111111111",
    "username": "user",
    "created_at": "2023-01-02T03:04:00+00:00",
    "global_role": "user",
    "email": None,
    "active": True,
    "permissions": {"can_create_projects": True},
    "ssh_public_key": None,
}


class TestUsersAPIClientList:
    def test_serializes_pagination_and_parses_info_list(self):
        recorder = RequestRecorder({"total_count": 1, "users": [USER_PAYLOAD]})
        client = UsersAPIClient(_request=recorder, _logger=logging.getLogger("test"))
        dt = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        uid = UUID("22222222-2222-4222-8222-222222222222")

        result = client.list(
            return_total_count=True,
            prev_created_at=dt,
            prev_id=uid,
            limit=1,
            ascending=True,
        )

        payload = json.loads(recorder.last_body)
        assert recorder.last_path == "/api/users/list"
        assert payload["return_total_count"] is True
        assert payload["prev_created_at"] == dt.isoformat()
        assert payload["prev_id"] == str(uid)
        assert payload["limit"] == 1
        assert payload["ascending"] is True
        assert result.total_count == 1
        assert result.users[0].username == "user"

    def test_parses_list_response(self):
        recorder = RequestRecorder([USER_PAYLOAD])
        client = UsersAPIClient(_request=recorder, _logger=logging.getLogger("test"))
        result = client.list()

        assert isinstance(result, list)
        assert result[0].username == "user"
