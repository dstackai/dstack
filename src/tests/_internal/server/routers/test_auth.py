import json
from base64 import b64encode

import pytest
from httpx import AsyncClient

from dstack._internal.core.models.auth import OAuthProviderInfo
from dstack._internal.server.services.auth import register_provider


class TestListProviders:
    @pytest.mark.asyncio
    async def test_returns_no_providers(self, client: AsyncClient):
        response = await client.post("/api/auth/list_providers")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_returns_registered_providers(self, client: AsyncClient):
        register_provider(OAuthProviderInfo(name="provider1", enabled=True))
        register_provider(OAuthProviderInfo(name="provider2", enabled=False))
        response = await client.post("/api/auth/list_providers")
        assert response.status_code == 200
        assert response.json() == [
            {
                "name": "provider1",
                "enabled": True,
            },
            {
                "name": "provider2",
                "enabled": False,
            },
        ]


class TestGetNextRedirectURL:
    @pytest.mark.asyncio
    async def test_returns_no_redirect_url_if_local_port_not_set(self, client: AsyncClient):
        state = b64encode(json.dumps({"value": "12356", "local_port": None}).encode()).decode()
        response = await client.post(
            "/api/auth/get_next_redirect", json={"code": "1234", "state": state}
        )
        assert response.status_code == 200
        assert response.json() == {"redirect_url": None}

    @pytest.mark.asyncio
    async def test_returns_redirect_url_if_local_port_set(self, client: AsyncClient):
        state = b64encode(json.dumps({"value": "12356", "local_port": 12345}).encode()).decode()
        response = await client.post(
            "/api/auth/get_next_redirect", json={"code": "1234", "state": state}
        )
        assert response.status_code == 200
        assert response.json() == {
            "redirect_url": f"http://localhost:12345/auth/callback?code=1234&state={state}"
        }

    @pytest.mark.asyncio
    async def test_returns_400_if_state_invalid(self, client: AsyncClient):
        state = "some_invalid_state"
        response = await client.post(
            "/api/auth/get_next_redirect", json={"code": "1234", "state": state}
        )
        assert response.status_code == 400
        assert "Invalid state token" in response.json()["detail"][0]["msg"]
