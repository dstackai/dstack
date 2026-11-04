from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.schemas.services import (
    ServiceListItem,
    ServiceListReplicaItem,
    ServiceListResponse,
)
from dstack._internal.proxy.lib.models import Service
from dstack._internal.utils.common import run_async


async def list_services(repo: GatewayProxyRepo) -> ServiceListResponse:
    services = await repo.list_services()
    # Parsing uncached head-node keys must not block other gateway API requests.
    return await run_async(_get_service_list_response, services)


def _get_service_list_response(services: list[Service]) -> ServiceListResponse:
    return ServiceListResponse(
        services=[
            ServiceListItem(
                id=service.id,
                project_name=service.project_name,
                run_name=service.run_name,
                replicas=[
                    ServiceListReplicaItem(
                        id=replica.id,
                        ssh_head_proxy_public_key=replica.ssh_head_proxy_public_key,
                    )
                    for replica in service.replicas
                ],
            )
            for service in services
        ]
    )
