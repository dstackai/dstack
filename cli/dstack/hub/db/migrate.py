from dstack.hub.db.models import Hub, User
from dstack.hub.db import Database


async def migrate():
    async with Database.engine.begin() as session:
        await session.run_sync(Hub.metadata.create_all)
        await session.run_sync(User.metadata.create_all)
