import json
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dstack.hub.db import Database
from dstack.hub.db.models import Hub
from dstack.hub.models import AWSBackend, HubInfo, Member

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


def hub2info(hub):
    members = []
    for member in hub.members:
        members.append(
            Member(
                user_name=member.user_name,
                hub_role=member.hub_role,
            )
        )
    backend = None
    if hub.backend == "aws":
        backend = aws(hub)
    return HubInfo(hub_name=hub.name, backend=backend, members=members)


def aws(hub) -> AWSBackend:
    backend = AWSBackend(type="aws")
    if hub.auth is not None:
        json_auth = json.loads(str(hub.auth))
        backend.access_key = json_auth.get("access_key") or ""
        backend.secret_key = json_auth.get("secret_key") or ""
    if hub.config is not None:
        json_config = json.loads(str(hub.config))
        backend.region_name = json_config.get("region_name") or ""
        backend.region_name_title = json_config.get("region_name") or ""
        backend.s3_bucket_name = (
            json_config.get("bucket_name") or json_config.get("s3_bucket_name") or ""
        )
        backend.ec2_subnet_id = (
            json_config.get("subnet_id") or json_config.get("ec2_subnet_id") or ""
        )
    return backend
