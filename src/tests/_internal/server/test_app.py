from typing import Optional
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal import settings
from dstack._internal.server.main import app
from dstack._internal.server.testing.common import create_user, get_auth_headers

client = TestClient(app)


class TestIndex:
    @pytest.mark.ui
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_html(self, test_db, session: AsyncSession, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        assert response.content.startswith(b'<!doctype html><html lang="en"><')


class TestCheckXApiVersion:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        ("client_version", "server_version", "is_compatible"),
        [
            ("12.12.12", None, True),
            ("0.12.4", "0.12.4", True),
            (None, "0.1.12", True),
            ("0.13.0", "0.12.4", False),
            # For test performance, only a few cases are covered here.
            # More cases are covered in `TestCheckClientServerCompatibility`.
        ],
    )
    @pytest.mark.parametrize("endpoint", ["/api/users/list", "/api/projects/list"])
    async def test_check_client_compatibility(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        endpoint: str,
        client_version: Optional[str],
        server_version: Optional[str],
        is_compatible: bool,
    ):
        user = await create_user(session=session)
        headers = get_auth_headers(user.token)
        if client_version is not None:
            headers["X-API-Version"] = client_version

        with patch.object(settings, "DSTACK_VERSION", server_version):
            response = await client.post(endpoint, headers=headers, json={})

        if is_compatible:
            assert response.status_code == 200, response.text
        else:
            assert response.status_code == 400
            assert response.json() == {
                "detail": [
                    {
                        "code": "error",
                        "msg": f"The client/CLI version ({client_version}) is incompatible with the server version ({server_version}).",
                    }
                ]
            }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize("endpoint", ["/api/users/list", "/api/projects/list"])
    @pytest.mark.parametrize("invalid_value", ["", "1..0", "version1"])
    async def test_invalid_x_api_version_header(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        endpoint: str,
        invalid_value: str,
    ):
        user = await create_user(session=session)
        headers = get_auth_headers(user.token)
        headers["X-API-Version"] = invalid_value

        response = await client.post(endpoint, headers=headers, json={})

        assert response.status_code == 400
        assert response.json() == {
            "detail": [
                {
                    "code": None,
                    "msg": f"Invalid version: {invalid_value}",
                }
            ]
        }
