from unittest.mock import patch

import pytest
from httpx import AsyncClient

from dstack._internal import settings


class TestGetInfo:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        with patch.object(settings, "DSTACK_VERSION", "0.18.10"):
            response = await client.post("/api/server/get_info")
        assert response.status_code == 200
        assert response.json() == {"server_version": "0.18.10"}
