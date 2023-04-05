import json
from typing import List

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from dstack.hub.db import get_or_make_session
from dstack.hub.db.models import Member, Project
from dstack.hub.models import (
    AWSProjectConfig,
    AWSProjectConfigWithCreds,
    AWSProjectCreds,
    GCPProjectConfig,
    GCPProjectConfigWithCreds,
    GCPProjectCreds,
    Member,
    ProjectInfo,
)
from dstack.hub.repository.role import RoleManager


class ProjectManager:
    @staticmethod
    async def get_project_info(name: str, external_session: Session = None) -> ProjectInfo:
        project = await ProjectManager.get(name, external_session=external_session)
        return _project2info(project=project)

    @staticmethod
    async def create_project_from_info(project_info: ProjectInfo, external_session=None):
        project = _info2project(project_info)
        await ProjectManager.create(project, external_session=external_session)

    @staticmethod
    async def update_project_from_info(project_info: ProjectInfo, external_session=None):
        project = _info2project(project_info)
        await ProjectManager.update(project, external_session=external_session)

    @staticmethod
    async def list_project_info(external_session=None) -> List[ProjectInfo]:
        session = get_or_make_session(external_session)
        query = await session.execute(select(Project).options(selectinload(Project.members)))
        projects = query.scalars().unique().all()
        projects_info = []
        for project in projects:
            projects_info.append(_project2info(project=project))
        if external_session is None:
            await session.close()
        return projects_info

    @staticmethod
    async def get(name: str, external_session=None) -> Project:
        session = get_or_make_session(external_session)
        query = await session.execute(
            select(Project).options(selectinload(Project.members)).where(Project.name == name)
        )
        project = query.scalars().unique().first()
        if external_session is None:
            await session.close()
        return project

    @staticmethod
    async def create(project: Project, external_session=None):
        session = get_or_make_session(external_session)
        session.add(project)
        await session.commit()
        if external_session is None:
            await session.close()

    @staticmethod
    async def update(project: Project, external_session=None):
        session = get_or_make_session(external_session)
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
        if external_session is None:
            await session.close()

    @staticmethod
    async def delete(project_name: str, external_session=None):
        session = get_or_make_session(external_session)
        await session.execute(delete(Project).where(Project.name == project_name))
        await session.commit()
        if external_session is None:
            await session.close()

    @staticmethod
    async def add_member(project: Project, member: Member, external_session=None):
        session = get_or_make_session(external_session)
        role = await RoleManager.get_or_create(name=member.project_role, external_session=session)
        session.add(Member(project_name=project.name, user_name=member.user_name, role_id=role.id))
        await session.commit()
        if external_session is None:
            await session.close()

    @staticmethod
    async def clear_member(project: Project, external_session=None):
        session = get_or_make_session(external_session)
        await session.execute(delete(Member).where(Member.project_name == project.name))
        await session.commit()
        if external_session is None:
            await session.close()


def _info2project(project_info: ProjectInfo) -> Project:
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


def _project2info(project: Project) -> ProjectInfo:
    members = []
    for member in project.members:
        members.append(
            Member(
                user_name=member.user_name,
                project_role=member.project_role.name,
            )
        )
    backend = None
    if project.backend == "aws":
        backend = _aws(project)
    if project.backend == "gcp":
        backend = _gcp(project)
    return ProjectInfo(project_name=project.name, backend=backend, members=members)


def _aws(project: Project) -> AWSProjectConfigWithCreds:
    json_auth = json.loads(project.auth)
    json_config = json.loads(project.config)
    access_key = json_auth["access_key"]
    secret_key = json_auth["secret_key"]
    region_name = json_config["region_name"]
    s3_bucket_name = json_config["s3_bucket_name"]
    ec2_subnet_id = json_config["ec2_subnet_id"]
    return AWSProjectConfigWithCreds(
        access_key=access_key,
        secret_key=secret_key,
        region_name=region_name,
        region_name_title=region_name,
        s3_bucket_name=s3_bucket_name,
        ec2_subnet_id=ec2_subnet_id,
    )


def _gcp(project: Project) -> GCPProjectConfigWithCreds:
    json_auth = json.loads(project.auth)
    json_config = json.loads(project.config)
    credentials = json_auth["credentials"]
    credentials_filename = json_auth["credentials_filename"]
    area = json_config["area"]
    region = json_config["region"]
    zone = json_config["zone"]
    bucket_name = json_config["bucket_name"]
    vpc = json_config["vpc"]
    subnet = json_config["subnet"]
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
