import json
from typing import List, Optional, Union

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dstack.hub.db import reuse_or_make_session
from dstack.hub.db.models import Member as MemberDB
from dstack.hub.db.models import Project, User
from dstack.hub.models import (
    AWSProjectConfig,
    AWSProjectConfigWithCreds,
    AWSProjectCreds,
    GCPProjectConfig,
    GCPProjectConfigWithCreds,
    GCPProjectCreds,
    Member,
    ProjectInfo,
    ProjectInfoWithCreds,
)
from dstack.hub.security.utils import ROLE_ADMIN


class ProjectManager:
    @staticmethod
    async def get_project_info_with_creds(project: Project) -> Optional[ProjectInfoWithCreds]:
        return _project2info(project=project, include_creds=True)

    @staticmethod
    async def get_project_info(project: Project) -> Optional[ProjectInfo]:
        return _project2info(project=project, include_creds=False)

    @staticmethod
    @reuse_or_make_session
    async def create_project_from_info(
        user: User, project_info: ProjectInfoWithCreds, session: Optional[AsyncSession] = None
    ):
        project = _info2project(project_info)
        await ProjectManager.create(project, session=session)
        await ProjectManager._add_member(
            project, Member(user_name=user.name, project_role=ROLE_ADMIN)
        )

    @staticmethod
    async def update_project_from_info(
        project_info: ProjectInfoWithCreds, session: Optional[AsyncSession] = None
    ):
        project = _info2project(project_info)
        await ProjectManager.update(project, session=session)

    @staticmethod
    @reuse_or_make_session
    async def list_project_info(session: Optional[AsyncSession] = None) -> List[ProjectInfo]:
        query = await session.execute(select(Project).options(selectinload(Project.members)))
        projects = query.scalars().unique().all()
        projects_info = []
        for project in projects:
            projects_info.append(_project2info(project=project))
        return projects_info

    @staticmethod
    @reuse_or_make_session
    async def get(name: str, session: Optional[AsyncSession] = None) -> Optional[Project]:
        query = await session.execute(
            select(Project).options(selectinload(Project.members)).where(Project.name == name)
        )
        project = query.scalars().unique().first()
        return project

    @staticmethod
    @reuse_or_make_session
    async def list(session: Optional[AsyncSession] = None) -> List[Project]:
        query = await session.execute(select(Project).options(selectinload(Project.members)))
        projects = query.scalars().unique().all()
        return projects

    @staticmethod
    @reuse_or_make_session
    async def create(project: Project, session: Optional[AsyncSession] = None):
        session.add(project)
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def update(project: Project, session: Optional[AsyncSession] = None):
        await session.execute(
            update(Project)
            .where(Project.name == project.name)
            .values(
                backend=project.backend,
                config=project.config,
                auth=project.auth,
            )
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def delete(project_name: str, session: Optional[AsyncSession] = None):
        await session.execute(delete(Project).where(Project.name == project_name))
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def get_member(
        user: User, project: Project, session: Optional[AsyncSession] = None
    ) -> Optional[MemberDB]:
        query = await session.execute(
            select(MemberDB).where(
                MemberDB.project_name == project.name, MemberDB.user_name == user.name
            )
        )
        return query.scalars().unique().first()

    @staticmethod
    @reuse_or_make_session
    async def set_members(
        project: Project, members: List[Member], session: Optional[AsyncSession] = None
    ) -> Optional[MemberDB]:
        await ProjectManager._clear_member(project, session=session)
        for member in members:
            await ProjectManager._add_member(project=project, member=member)

    @staticmethod
    @reuse_or_make_session
    async def _add_member(
        project: Project, member: Member, session: Optional[AsyncSession] = None
    ):
        session.add(
            MemberDB(
                project_name=project.name,
                user_name=member.user_name,
                project_role=member.project_role,
            )
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def _clear_member(project: Project, session: Optional[AsyncSession] = None):
        await session.execute(delete(MemberDB).where(MemberDB.project_name == project.name))
        await session.commit()


def _info2project(project_info: ProjectInfoWithCreds) -> Project:
    project_info.backend = project_info.backend.__root__
    project = Project(
        name=project_info.project_name,
        backend=project_info.backend.type,
    )
    if project_info.backend.type == "aws":
        project_info.backend.s3_bucket_name = project_info.backend.s3_bucket_name.replace(
            "s3://", ""
        )
        project.config = AWSProjectConfig.parse_obj(project_info.backend).json()
        project.auth = AWSProjectCreds.parse_obj(project_info.backend).json()
    if project_info.backend.type == "gcp":
        project.config = GCPProjectConfig.parse_obj(project_info.backend).json()
        project.auth = GCPProjectCreds.parse_obj(project_info.backend).json()
    return project


def _project2info(
    project: Project, include_creds: bool = False
) -> Union[ProjectInfo, ProjectInfoWithCreds]:
    members = []
    for member in project.members:
        members.append(
            Member(
                user_name=member.user_name,
                project_role=member.project_role,
            )
        )
    backend = None
    if project.backend == "aws":
        backend = _aws(project, include_creds=include_creds)
    if project.backend == "gcp":
        backend = _gcp(project, include_creds=include_creds)
    if include_creds:
        return ProjectInfoWithCreds(project_name=project.name, backend=backend, members=members)
    return ProjectInfo(project_name=project.name, backend=backend, members=members)


def _aws(
    project: Project, include_creds: bool
) -> Union[AWSProjectConfig, AWSProjectConfigWithCreds]:
    json_config = json.loads(project.config)
    region_name = json_config["region_name"]
    s3_bucket_name = json_config["s3_bucket_name"]
    ec2_subnet_id = json_config["ec2_subnet_id"]
    if include_creds:
        json_auth = json.loads(project.auth)
        access_key = json_auth["access_key"]
        secret_key = json_auth["secret_key"]
        return AWSProjectConfigWithCreds(
            access_key=access_key,
            secret_key=secret_key,
            region_name=region_name,
            region_name_title=region_name,
            s3_bucket_name=s3_bucket_name,
            ec2_subnet_id=ec2_subnet_id,
        )
    return AWSProjectConfig(
        region_name=region_name,
        region_name_title=region_name,
        s3_bucket_name=s3_bucket_name,
        ec2_subnet_id=ec2_subnet_id,
    )


def _gcp(
    project: Project, include_creds: bool
) -> Union[GCPProjectConfig, GCPProjectConfigWithCreds]:
    json_config = json.loads(project.config)
    area = json_config["area"]
    region = json_config["region"]
    zone = json_config["zone"]
    bucket_name = json_config["bucket_name"]
    vpc = json_config["vpc"]
    subnet = json_config["subnet"]
    if include_creds:
        json_auth = json.loads(project.auth)
        credentials = json_auth["credentials"]
        credentials_filename = json_auth["credentials_filename"]
        return GCPProjectConfigWithCreds(
            credentials=credentials,
            credentials_filename=credentials_filename,
            area=area,
            region=region,
            zone=zone,
            bucket_name=bucket_name,
            vpc=vpc,
            subnet=subnet,
        )
    return GCPProjectConfig(
        area=area,
        region=region,
        zone=zone,
        bucket_name=bucket_name,
        vpc=vpc,
        subnet=subnet,
    )
