from unittest.mock import Mock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server.models import FileArchiveModel
from dstack._internal.server.services.storage import BaseStorage
from dstack._internal.server.testing.common import (
    create_file_archive,
    create_user,
    get_auth_headers,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("test_db"),
    pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True),
]


class TestGetArchiveByHash:
    async def test_returns_403_if_not_authenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/files/get_archive_by_hash",
            json={"hash": "blob_hash"},
        )
        assert response.status_code == 403

    async def test_returns_400_if_archive_does_not_exist(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        response = await client.post(
            "/api/files/get_archive_by_hash",
            headers=get_auth_headers(user.token),
            json={"hash": "blob_hash"},
        )
        assert response.status_code == 400, response.json()

    async def test_returns_archive(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        archive = await create_file_archive(
            session=session, user_id=user.id, blob_hash="blob_hash", blob=b"blob_content"
        )
        response = await client.post(
            "/api/files/get_archive_by_hash",
            headers=get_auth_headers(user.token),
            json={"hash": archive.blob_hash},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "id": str(archive.id),
            "hash": archive.blob_hash,
        }


class TestUploadArchive:
    file_hash = "blob_hash"
    file_content = b"blob_content"
    file = (file_hash, file_content)

    @pytest.fixture
    def default_storage_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        storage_mock = Mock(spec_set=BaseStorage)
        monkeypatch.setattr(
            "dstack._internal.server.services.files.get_default_storage", lambda: storage_mock
        )
        return storage_mock

    @pytest.fixture
    def no_default_storage(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "dstack._internal.server.services.files.get_default_storage", lambda: None
        )

    async def test_returns_403_if_not_authenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/files/upload_archive",
            files={"file": self.file},
        )
        assert response.status_code == 403

    async def test_returns_existing_archive(
        self, session: AsyncSession, client: AsyncClient, default_storage_mock: Mock
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        existing_archive = await create_file_archive(
            session=session, user_id=user.id, blob_hash=self.file_hash, blob=b"existing_blob"
        )
        response = await client.post(
            "/api/files/upload_archive",
            headers=get_auth_headers(user.token),
            files={"file": self.file},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "id": str(existing_archive.id),
            "hash": self.file_hash,
        }
        res = await session.execute(
            select(FileArchiveModel).where(FileArchiveModel.user_id == user.id)
        )
        archive = res.scalar_one()
        assert archive.id == existing_archive.id
        assert archive.blob_hash == self.file_hash
        assert archive.blob == existing_archive.blob
        default_storage_mock.upload_archive.assert_not_called()

    @pytest.mark.usefixtures("no_default_storage")
    async def test_uploads_archive_to_db(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        response = await client.post(
            "/api/files/upload_archive",
            headers=get_auth_headers(user.token),
            files={"file": self.file},
        )
        assert response.status_code == 200, response.json()
        assert response.json()["hash"] == self.file_hash
        res = await session.execute(
            select(FileArchiveModel).where(FileArchiveModel.user_id == user.id)
        )
        archive = res.scalar_one()
        assert archive.blob_hash == self.file_hash
        assert archive.blob == self.file_content

    async def test_uploads_archive_to_storage(
        self, session: AsyncSession, client: AsyncClient, default_storage_mock: Mock
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        response = await client.post(
            "/api/files/upload_archive",
            headers=get_auth_headers(user.token),
            files={"file": self.file},
        )
        assert response.status_code == 200, response.json()
        assert response.json()["hash"] == self.file_hash
        res = await session.execute(
            select(FileArchiveModel).where(FileArchiveModel.user_id == user.id)
        )
        archive = res.scalar_one()
        assert archive.blob_hash == self.file_hash
        assert archive.blob is None
        default_storage_mock.upload_archive.assert_called_once_with(
            str(user.id), self.file_hash, self.file_content
        )
