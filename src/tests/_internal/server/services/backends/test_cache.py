import asyncio
import uuid
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.errors import BackendNotAvailable
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends import cache as backends_cache


def make_backend_model(backend_type: BackendType, config: str = "{}") -> BackendModel:
    backend_model = SimpleNamespace(
        id=uuid.uuid4(),
        type=backend_type,
        config=config,
        auth=SimpleNamespace(decrypted=True),
    )
    return cast(BackendModel, backend_model)


def make_project(*backend_models: BackendModel) -> ProjectModel:
    project = SimpleNamespace(id=uuid.uuid4(), backends=list(backend_models))
    return cast(ProjectModel, project)


def close_mock(backend: Backend) -> Mock:
    return cast(Mock, backend.close)


async def close_unused_backends_now(monkeypatch: pytest.MonkeyPatch):
    """
    Closes all backends that are not leased, as if they all were idle.
    """
    monkeypatch.setattr(backends_cache, "_BACKEND_IDLE_TTL", -1)
    await backends_cache.close_unused_backends()


class TestBackendsCache:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        monkeypatch.setattr(backends_cache, "_BACKENDS_CACHE", {})
        monkeypatch.setattr(backends_cache, "_BACKENDS_CACHE_LOCKS", {})
        monkeypatch.setattr(backends_cache, "get_stored_backend_record", lambda m: m)
        self.backends: list[Mock] = []

        def get_backend(backend_model):
            backend = Mock(TYPE=backend_model.type)
            self.backends.append(backend)
            return backend

        monkeypatch.setattr(
            backends_cache,
            "get_configurator",
            lambda backend_type: Mock(get_backend=Mock(side_effect=get_backend)),
        )

    @pytest.mark.asyncio
    async def test_reuses_backends_between_leases(self):
        project = make_project(make_backend_model(BackendType.AWS))
        async with backends_cache.lease_project_backends(project) as first:
            pass
        async with backends_cache.lease_project_backends(project) as second:
            pass
        assert first == second == self.backends
        self.backends[0].close.assert_not_called()

    @pytest.mark.asyncio
    async def test_closes_backend_with_changed_config_after_release(self):
        project = make_project(make_backend_model(BackendType.AWS, config="old"))
        async with backends_cache.lease_project_backends(project) as [old_backend]:
            project.backends = [make_backend_model(BackendType.AWS, config="new")]
            async with backends_cache.lease_project_backends(project) as [new_backend]:
                assert new_backend is not old_backend
            await backends_cache.close_unused_backends()
            close_mock(old_backend).assert_not_called()
        await backends_cache.close_unused_backends()
        close_mock(old_backend).assert_called_once()
        close_mock(new_backend).assert_not_called()

    @pytest.mark.asyncio
    async def test_closes_deleted_backend(self):
        project = make_project(
            make_backend_model(BackendType.AWS), make_backend_model(BackendType.GCP)
        )
        async with backends_cache.lease_project_backends(project):
            pass
        aws_backend, gcp_backend = self.backends
        project.backends = project.backends[:1]
        async with backends_cache.lease_project_backends(project) as backends:
            assert backends == [aws_backend]
        await backends_cache.close_unused_backends()
        close_mock(gcp_backend).assert_called_once()
        close_mock(aws_backend).assert_not_called()

    @pytest.mark.asyncio
    async def test_closes_idle_backends(self, monkeypatch):
        project = make_project(
            make_backend_model(BackendType.AWS), make_backend_model(BackendType.GCP)
        )
        async with backends_cache.lease_project_backends(project):
            pass
        aws_backend, gcp_backend = self.backends
        async with backends_cache.lease_project_backend_by_type(
            project, BackendType.AWS
        ) as backend:
            assert backend is aws_backend
            # Only GCP is idle: AWS is leased and was used just now
            monkeypatch.setattr(backends_cache, "_BACKEND_IDLE_TTL", 0)
            await backends_cache.close_unused_backends()
        close_mock(gcp_backend).assert_called_once()
        close_mock(aws_backend).assert_not_called()

    @pytest.mark.asyncio
    async def test_selecting_backend_does_not_refresh_other_backends(self, monkeypatch):
        project = make_project(
            make_backend_model(BackendType.AWS), make_backend_model(BackendType.GCP)
        )
        async with backends_cache.lease_project_backends(project):
            pass
        aws_backend, gcp_backend = self.backends
        monkeypatch.setattr(backends_cache, "_BACKEND_IDLE_TTL", 0)
        async with backends_cache.lease_project_backend_by_type(project, BackendType.AWS):
            await backends_cache.close_unused_backends()
        close_mock(gcp_backend).assert_called_once()
        close_mock(aws_backend).assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_close_leased_backends(self, monkeypatch):
        project = make_project(make_backend_model(BackendType.AWS))
        async with backends_cache.lease_project_backends(project) as [backend]:
            await close_unused_backends_now(monkeypatch)
            close_mock(backend).assert_not_called()
        await close_unused_backends_now(monkeypatch)
        close_mock(backend).assert_called_once()

    @pytest.mark.asyncio
    async def test_releases_lease_if_cancelled(self, monkeypatch):
        project = make_project(make_backend_model(BackendType.AWS))
        leased = asyncio.Event()

        async def hold_lease():
            async with backends_cache.lease_project_backends(project):
                leased.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(hold_lease())
        await leased.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await close_unused_backends_now(monkeypatch)
        close_mock(self.backends[0]).assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_raise_if_backend_fails_to_close(self, monkeypatch):
        project = make_project(make_backend_model(BackendType.AWS))
        async with backends_cache.lease_project_backends(project) as [backend]:
            close_mock(backend).side_effect = RuntimeError("close failed")
        await close_unused_backends_now(monkeypatch)
        close_mock(backend).assert_called_once()

    @pytest.mark.asyncio
    async def test_or_error_raises_and_releases_leases(self, monkeypatch):
        project = make_project(make_backend_model(BackendType.AWS))
        with pytest.raises(BackendNotAvailable):
            async with backends_cache.lease_project_backend_by_type_or_error(
                project, BackendType.GCP
            ):
                pass
        [aws_backend] = self.backends
        await close_unused_backends_now(monkeypatch)
        close_mock(aws_backend).assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_selector_with_overrides(self, monkeypatch):
        project = make_project(make_backend_model(BackendType.DSTACK))

        async def select(project, backend_type, backends_with_models):
            return backends_with_models[0]

        monkeypatch.setattr(backends_cache, "_select_project_backend_with_model_by_type", select)
        async with backends_cache.lease_project_backend_by_type(
            project, BackendType.AWS, overrides=True
        ) as backend:
            assert backend is self.backends[0]
        async with backends_cache.lease_project_backend_by_type(
            project, BackendType.AWS
        ) as backend:
            assert backend is None

    @pytest.mark.asyncio
    async def test_releases_leases_if_selector_fails(self, monkeypatch):
        project = make_project(make_backend_model(BackendType.DSTACK))

        async def select(project, backend_type, backends_with_models):
            raise RuntimeError("select failed")

        monkeypatch.setattr(backends_cache, "_select_project_backend_with_model_by_type", select)
        with pytest.raises(RuntimeError):
            async with backends_cache.lease_project_backend_by_type(
                project, BackendType.AWS, overrides=True
            ):
                pass
        await close_unused_backends_now(monkeypatch)
        close_mock(self.backends[0]).assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_and_releases_leases_if_selector_returns_unknown_backend(
        self, monkeypatch
    ):
        project = make_project(make_backend_model(BackendType.DSTACK))

        async def select(project, backend_type, backends_with_models):
            return backends_with_models[0][0], Mock()

        monkeypatch.setattr(backends_cache, "_select_project_backend_with_model_by_type", select)
        with pytest.raises(ValueError):
            async with backends_cache.lease_project_backend_by_type(
                project, BackendType.AWS, overrides=True
            ):
                pass
        await close_unused_backends_now(monkeypatch)
        close_mock(self.backends[0]).assert_called_once()
