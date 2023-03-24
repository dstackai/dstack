import json

from dstack.hub.db.models import Project
from dstack.hub.models import AWSAuth, AWSBackend, AWSConfig, Member, ProjectInfo


def info2project(project_info: ProjectInfo) -> Project:
    project = Project(
        name=project_info.project_name,
        backend=project_info.backend.type,
    )
    if project_info.backend.type == "aws":
        project_info.backend.s3_bucket_name = project_info.backend.s3_bucket_name.replace(
            "s3://", ""
        )
        project.config = AWSConfig().parse_obj(project_info.backend).json()
        project.auth = AWSAuth().parse_obj(project_info.backend).json()
    return project


def project2info(project: Project) -> ProjectInfo:
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
    return ProjectInfo(project_name=project.name, backend=backend, members=members)


def _aws(project) -> AWSBackend:
    backend = AWSBackend(type="aws")
    if project.auth is not None:
        json_auth = json.loads(str(project.auth))
        backend.access_key = json_auth.get("access_key") or ""
        backend.secret_key = json_auth.get("secret_key") or ""
    if project.config is not None:
        json_config = json.loads(str(project.config))
        backend.region_name = json_config.get("region_name") or ""
        backend.region_name_title = json_config.get("region_name") or ""
        backend.s3_bucket_name = (
            json_config.get("bucket_name") or json_config.get("s3_bucket_name") or ""
        )
        backend.ec2_subnet_id = (
            json_config.get("subnet_id") or json_config.get("ec2_subnet_id") or ""
        )
    return backend
