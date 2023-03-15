import json
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from dstack.hub.db import Database
from dstack.hub.db.models import Hub as HubDB
from dstack.hub.db.models import Member as MemberDB
from dstack.hub.models import HubInfo, Member
from dstack.hub.repository.role import RoleManager
from dstack.hub.util import hub2info


class HubManager:
    @staticmethod
    async def get_info(name: str, external_session=None) -> HubInfo:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        query = await _session.execute(
            select(HubDB).options(selectinload(HubDB.members)).where(HubDB.name == name)
        )
        hub = query.scalars().unique().first()
        hub_info = hub2info(hub=hub)
        if external_session is None:
            await _session.close()
        return hub_info

    @staticmethod
    async def get(name: str, external_session=None) -> HubDB:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        query = await _session.execute(
            select(HubDB).options(selectinload(HubDB.members)).where(HubDB.name == name)
        )
        hub = query.scalars().unique().first()
        if external_session is None:
            await _session.close()
        return hub

    @staticmethod
    async def save(hub: HubDB, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        _session.add(hub)
        await _session.commit()
        if external_session is None:
            await _session.close()

    @staticmethod
    async def remove(hub: HubDB, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        await _session.execute(delete(HubDB).where(HubDB.name == hub.name))
        await _session.commit()
        if external_session is None:
            await _session.close()

    @staticmethod
    async def list_info(external_session=None) -> List[HubInfo]:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        query = await _session.execute(select(HubDB).options(selectinload(HubDB.members)))
        hubs = query.scalars().unique().all()
        hubs_info = []
        for hub in hubs:
            hubs_info.append(hub2info(hub=hub))
        if external_session is None:
            await _session.close()
        return hubs_info

    @staticmethod
    async def add_member(hub: HubDB, member: Member, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        role = await RoleManager.get_by_name(name=member.hub_role, external_session=_session)
        _session.add(MemberDB(hub_name=hub.name, user_name=member.user_name, role_id=role.id))
        await _session.commit()
        if external_session is None:
            await _session.close()

    @staticmethod
    async def clear_member(hub: HubDB, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        await _session.execute(delete(MemberDB).where(MemberDB.hub_name == hub.name))
        await _session.commit()
        if external_session is None:
            await _session.close()
