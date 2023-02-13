from typing import List

from sqlalchemy import select

from dstack.hub.db import Database
from dstack.hub.db.models import Hub
from dstack.hub.models import HubInfo

session = Database.Session()


class HubManager:
    @staticmethod
    async def get_info(name: str) -> HubInfo:
        query = await session.execute(select(Hub).where(Hub.name == name))
        hub = query.scalars().first()
        return HubInfo(name=hub.name, backend=hub.backend)

    @staticmethod
    async def get(name: str) -> Hub:
        query = await session.execute(select(Hub).where(Hub.name == name))
        hub = query.scalars().first()
        return hub

    @staticmethod
    async def save(hub: Hub):
        session.add(hub)
        await session.commit()

    @staticmethod
    async def remove(hub: Hub):
        session.delete(hub)
        await session.commit()

    @staticmethod
    async def list_info() -> List[HubInfo]:
        query = await session.execute(select(Hub))
        hubs = query.scalars().all()
        hubs_info = []
        for hub in hubs:
            hubs_info.append(HubInfo(name=hub.name, backend=hub.backend))
        return hubs_info
