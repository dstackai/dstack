from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.background.scheduled_tasks import orphan_cleanup_enrollment
from dstack._internal.server.background.scheduled_tasks.orphan_cleanup_enrollment import (
    enroll_backends_in_orphan_cleanup,
)
from dstack._internal.server.models import OrphanCleanupModel, ProjectModel, UserModel
from dstack._internal.server.testing.common import (
    create_backend,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
)


async def _list_enrolled_backend_ids(session: AsyncSession) -> set:
    res = await session.execute(select(OrphanCleanupModel.backend_id))
    return set(res.scalars().all())


async def _create_project_with_provider_ref_instance(
    session: AsyncSession,
    owner: UserModel,
    provider_ref: str,
    name: str = "test_project",
    deleted: bool = False,
) -> ProjectModel:
    project = await create_project(session=session, owner=owner, name=name, deleted=deleted)
    instance = await create_instance(session=session, project=project)
    instance.provider_ref = provider_ref
    await session.commit()
    return project


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestEnrollBackendsInOrphanCleanup:
    async def test_enrolls_backend_of_project_with_provider_ref_instance(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session)
        project = await _create_project_with_provider_ref_instance(session, user, "instref00001")
        backend = await create_backend(session=session, project_id=project.id)
        await enroll_backends_in_orphan_cleanup()
        res = await session.execute(select(OrphanCleanupModel))
        orphan_cleanup = res.scalar_one()
        assert orphan_cleanup.backend_id == backend.id
        assert orphan_cleanup.cleanup_attempt == 0
        assert orphan_cleanup.clean_at is None
        assert orphan_cleanup.last_processed_at == orphan_cleanup.created_at

    async def test_enrolls_backend_of_project_with_provider_ref_job(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        await create_job(session=session, run=run, provider_ref="jobref000001")
        backend = await create_backend(session=session, project_id=project.id)
        await enroll_backends_in_orphan_cleanup()
        assert await _list_enrolled_backend_ids(session) == {backend.id}

    async def test_skips_backends_that_cannot_be_cleaned_up(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project_without_refs = await create_project(session=session, owner=user, name="no-refs")
        await create_instance(session=session, project=project_without_refs)
        await create_backend(session=session, project_id=project_without_refs.id)
        deleted_project = await _create_project_with_provider_ref_instance(
            session, user, "instref00001", name="deleted", deleted=True
        )
        await create_backend(session=session, project_id=deleted_project.id)
        # Backend type without resource listing support
        project = await _create_project_with_provider_ref_instance(session, user, "instref00002")
        await create_backend(
            session=session, project_id=project.id, backend_type=BackendType.LAMBDA
        )
        await enroll_backends_in_orphan_cleanup()
        assert await _list_enrolled_backend_ids(session) == set()

    async def test_enrolls_limited_number_of_backends_per_run(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session)
        project = await _create_project_with_provider_ref_instance(session, user, "instref00001")
        backend = await create_backend(session=session, project_id=project.id)
        other_project = await _create_project_with_provider_ref_instance(
            session, user, "instref00002", name="other"
        )
        other_backend = await create_backend(session=session, project_id=other_project.id)
        with patch.object(orphan_cleanup_enrollment, "_ENROLLMENT_BATCH_SIZE", 1):
            await enroll_backends_in_orphan_cleanup()
            assert len(await _list_enrolled_backend_ids(session)) == 1
            await enroll_backends_in_orphan_cleanup()
        assert await _list_enrolled_backend_ids(session) == {backend.id, other_backend.id}

    async def test_is_idempotent(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await _create_project_with_provider_ref_instance(session, user, "instref00001")
        await create_backend(session=session, project_id=project.id)
        await enroll_backends_in_orphan_cleanup()
        res = await session.execute(select(OrphanCleanupModel))
        orphan_cleanup = res.scalar_one()
        await enroll_backends_in_orphan_cleanup()
        res = await session.execute(select(OrphanCleanupModel))
        assert [r.id for r in res.scalars().all()] == [orphan_cleanup.id]

    async def test_tolerates_backends_enrolled_concurrently(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await _create_project_with_provider_ref_instance(session, user, "instref00001")
        backend = await create_backend(session=session, project_id=project.id)
        other_project = await _create_project_with_provider_ref_instance(
            session, user, "instref00002", name="other"
        )
        other_backend = await create_backend(session=session, project_id=other_project.id)
        session.add(OrphanCleanupModel(backend_id=backend.id))
        await session.commit()
        # Another replica enrolls `backend` between the query and the insert
        with patch.object(
            orphan_cleanup_enrollment,
            "_select_backend_ids_to_enroll",
            AsyncMock(return_value=[backend.id, other_backend.id]),
        ):
            await enroll_backends_in_orphan_cleanup()
        assert await _list_enrolled_backend_ids(session) == {backend.id, other_backend.id}
