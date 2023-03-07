from dstack.hub.db import Database
from dstack.hub.db.models import Hub, Member, Role, Scope, User, association_table_user_hub


async def migrate():
    async with Database.engine.begin() as session:
        await session.run_sync(Hub.metadata.create_all)
        await session.run_sync(User.metadata.create_all)
        await session.run_sync(Role.metadata.create_all)
        await session.run_sync(Scope.metadata.create_all)
        await session.run_sync(association_table_user_hub.metadata.create_all)
        await session.run_sync(Member.metadata.create_all)
