import json

from dstack.hub.db.models import Project
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


def info2project(project_info: ProjectInfo) -> Project:
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
