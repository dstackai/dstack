from dstack.hub.db import Database
from dstack.hub.db.models import Hub, Role, Scope, User, association_table_user_role


async def migrate():
    async with Database.engine.begin() as session:
        await session.run_sync(Hub.metadata.create_all)
        await session.run_sync(User.metadata.create_all)
        await session.run_sync(Role.metadata.create_all)
        await session.run_sync(Scope.metadata.create_all)
        await session.run_sync(association_table_user_role.metadata.create_all)
