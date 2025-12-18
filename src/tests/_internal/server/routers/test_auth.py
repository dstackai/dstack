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
