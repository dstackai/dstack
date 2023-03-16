from dstack.hub.db import Database
from dstack.hub.db.models import Member, Project, Role, Scope, User, association_table_user_project


async def migrate():
    async with Database.engine.begin() as session:
        await session.run_sync(Project.metadata.create_all)
        await session.run_sync(User.metadata.create_all)
        await session.run_sync(Role.metadata.create_all)
        await session.run_sync(Scope.metadata.create_all)
        await session.run_sync(association_table_user_project.metadata.create_all)
        await session.run_sync(Member.metadata.create_all)
