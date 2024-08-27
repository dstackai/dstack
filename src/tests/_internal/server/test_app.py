import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.main import app

client = TestClient(app)


class TestIndex:
    @pytest.mark.ui
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_html(self, test_db, session: AsyncSession, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        assert response.content.startswith(b'<!doctype html><html lang="en"><')
