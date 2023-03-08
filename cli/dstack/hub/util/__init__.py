import json
from dstack.hub.models import Member, HubInfo, AWSBackend, AWSConfig, AWSAuth
from dstack.hub.db.models import Hub


def info2hub(hub_info: HubInfo) -> Hub:
    hub = Hub(
        name=hub_info.hub_name,
        backend=hub_info.backend.type,
    )
    if hub_info.backend.type == "aws":
        hub_info.backend.s3_bucket_name = hub_info.backend.s3_bucket_name.replace("s3://", "")
        hub.config = AWSConfig().parse_obj(hub_info.backend).json()
        hub.auth = AWSAuth().parse_obj(hub_info.backend).json()
    return hub


def hub2info(hub: Hub) -> HubInfo:
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
        backend = _aws(hub)
    return HubInfo(hub_name=hub.name, backend=backend, members=members)


def _aws(hub) -> AWSBackend:
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
