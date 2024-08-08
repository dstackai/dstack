import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.main import app

client = TestClient(app)


class TestIndex:
    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_returns_html(self, test_db, session: AsyncSession):
        response = client.get("/")
        assert response.status_code == 200
        assert response.content.startswith(b'<!doctype html><html lang="en"><')
