import json
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dstack.hub.db import Database
from dstack.hub.db.models import Hub
from dstack.hub.models import HubInfo
from dstack.hub.util import hub2info

session = Database.Session()


class HubManager:
    @staticmethod
    async def get_info(name: str, external_session=None) -> HubInfo:
        _session = session
        if external_session is not None:
            _session = external_session
        query = await _session.execute(
            select(Hub).options(selectinload(Hub.members)).where(Hub.name == name)
        )
        hub = query.scalars().unique().first()
        return hub2info(hub=hub)

    @staticmethod
    async def get(name: str, external_session=None) -> Hub:
        _session = session
        if external_session is not None:
            _session = external_session
        query = await _session.execute(
            select(Hub).options(selectinload(Hub.members)).where(Hub.name == name)
        )
        hub = query.scalars().unique().first()
        return hub

    @staticmethod
    async def save(hub: Hub, external_session=None):
        _session = session
        if external_session is not None:
            _session = external_session
        _session.add(hub)
        await _session.commit()

    @staticmethod
    async def remove(hub: Hub, external_session=None):
        _session = session
        if external_session is not None:
            _session = external_session
        _session.delete(hub)
        await _session.commit()

    @staticmethod
    async def list_info(external_session=None) -> List[HubInfo]:
        _session = session
        if external_session is not None:
            _session = external_session
        query = await _session.execute(select(Hub).options(selectinload(Hub.members)))
        hubs = query.scalars().unique().all()
        hubs_info = []
        for hub in hubs:
            hubs_info.append(hub2info(hub=hub))
        return hubs_info
