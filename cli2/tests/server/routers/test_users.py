import pytest
from fastapi.testclient import TestClient

from dstack._internal.server.main import app

client = TestClient(app)


class TestListUsers:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/users/list")
        assert response.status_code in [401, 403]
