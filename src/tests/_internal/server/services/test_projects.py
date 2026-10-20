import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import ProjectRole
from dstack._internal.server.models import MemberModel, UserModel
from dstack._internal.server.services import projects as projects_services
from dstack._internal.server.testing.common import create_project, create_user


class TestListUserAccessibleProjects:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_bounds_queries_and_loaded_members_to_page(self, test_db, session: AsyncSession):
        owner = await create_user(session=session, name="owner")
        member = await create_user(session=session, name="member")
        other_member = await create_user(session=session, name="other_member")
        for index in range(3):
            project = await create_project(session=session, owner=owner, name=f"project{index}")
            for user in (owner, member, other_member):
                await projects_services.add_project_member(
                    session=session, project=project, user=user, project_role=ProjectRole.USER
                )
        owner_id = owner.id
        member_id = member.id
        member_name = member.name
        session.expunge_all()
        owner = await session.get(UserModel, owner_id)
        assert owner is not None
        statements = []
        loaded_member_user_ids = []

        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        def loaded_as_persistent(session, instance):
            if isinstance(instance, MemberModel):
                loaded_member_user_ids.append(instance.user_id)

        event.listen(test_db.engine.sync_engine, "before_cursor_execute", before_cursor_execute)
        event.listen(session.sync_session, "loaded_as_persistent", loaded_as_persistent)
        try:
            result = await projects_services.list_user_accessible_projects(
                session=session,
                user=owner,
                include_not_joined=True,
                return_total_count=True,
                name_pattern=None,
                prev_created_at=None,
                prev_id=None,
                limit=2,
                ascending=False,
                username=member_name,
            )
        finally:
            event.remove(
                test_db.engine.sync_engine, "before_cursor_execute", before_cursor_execute
            )
            event.remove(session.sync_session, "loaded_as_persistent", loaded_as_persistent)

        projects = result if isinstance(result, list) else result.projects
        assert len(projects) == 2
        # No per-project queries or materialization of other users' memberships.
        assert len(statements) == 2
        assert loaded_member_user_ids == [member_id] * 2
