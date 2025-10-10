import asyncio
from asyncio import Lock
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import dstack._internal.proxy.gateway.schemas.registry as schemas
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.proxy.gateway import models as gateway_models
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.nginx import (
    LimitReqConfig,
    LimitReqZoneConfig,
    LocationConfig,
    ModelEntrypointConfig,
    Nginx,
    ReplicaConfig,
    ServiceConfig,
)
from dstack._internal.proxy.lib import models
from dstack._internal.proxy.lib.errors import ProxyError, UnexpectedProxyError
from dstack._internal.proxy.lib.repo import BaseProxyRepo
from dstack._internal.proxy.lib.services.service_connection import (
    ServiceConnection,
    ServiceConnectionPool,
)
from dstack._internal.utils.logging import get_logger

ACCESS_LOG_PATH = Path("/var/log/nginx/dstack.access.log")
logger = get_logger(__name__)
lock = Lock()


async def register_service(
    project_name: str,
    run_name: str,
    domain: str,
    https: bool,
    rate_limits: tuple[models.RateLimit, ...],
    auth: bool,
    client_max_body_size: int,
    model: Optional[schemas.AnyModel],
    ssh_private_key: str,
    repo: GatewayProxyRepo,
    nginx: Nginx,
    service_conn_pool: ServiceConnectionPool,
) -> None:
    service = models.Service(
        project_name=project_name,
        run_name=run_name,
        domain=domain,
        https=https,
        rate_limits=rate_limits,
        auth=auth,
        client_max_body_size=client_max_body_size,
        replicas=(),
    )

    async with lock:
        if await repo.get_service(project_name, run_name) is not None:
            raise ProxyError(f"Service {service.fmt()} is already registered")

        old_project = await repo.get_project(project_name)
        new_project = models.Project(name=project_name, ssh_private_key=ssh_private_key)
        if old_project is not None and old_project.ssh_private_key != new_project.ssh_private_key:
            logger.warning(
                "SSH key for service %s is different from the previous one", service.fmt()
            )
        await repo.set_project(new_project)

        logger.debug("Registering service %s", service.fmt())

        await apply_service(
            service=service,
            old_service=None,
            repo=repo,
            nginx=nginx,
            service_conn_pool=service_conn_pool,
        )
        await repo.set_service(service)

        if model is not None:
            await repo.set_model(
                models.ChatModel(
                    project_name=project_name,
                    name=model.name,
                    created_at=datetime.now(),
                    run_name=run_name,
                    format_spec=model_schema_to_format_spec(model),
                ),
            )

    logger.info("Service %s is registered now", service.fmt())


async def unregister_service(
    project_name: str,
    run_name: str,
    repo: GatewayProxyRepo,
    nginx: Nginx,
    service_conn_pool: ServiceConnectionPool,
) -> None:
    async with lock:
        service = await repo.get_service(project_name, run_name)
        if service is None:
            raise ProxyError(
                f"Service {project_name}/{run_name} is not registered, cannot unregister"
            )

        logger.debug("Unregistering service %s", service.fmt())

        await stop_replica_connections(
            ids=(r.id for r in service.replicas),
            service_conn_pool=service_conn_pool,
        )
        await nginx.unregister(service.domain_safe)
        await repo.delete_models_by_run(project_name, run_name)
        await repo.delete_service(project_name, run_name)

    logger.info("Service %s is unregistered now", service.fmt())


async def register_replica(
    project_name: str,
    run_name: str,
    replica_id: str,
    app_port: int,
    ssh_destination: str,
    ssh_port: int,
    ssh_proxy: Optional[SSHConnectionParams],
    ssh_head_proxy: Optional[SSHConnectionParams],
    ssh_head_proxy_private_key: Optional[str],
    repo: GatewayProxyRepo,
    nginx: Nginx,
    service_conn_pool: ServiceConnectionPool,
) -> None:
    replica = models.Replica(
        id=replica_id,
        app_port=app_port,
        ssh_destination=ssh_destination,
        ssh_port=ssh_port,
        ssh_proxy=ssh_proxy,
        ssh_head_proxy=ssh_head_proxy,
        ssh_head_proxy_private_key=ssh_head_proxy_private_key,
    )

    async with lock:
        old_service = await repo.get_service(project_name, run_name)
        if old_service is None:
            raise ProxyError(
                f"Service {project_name}/{run_name} does not exist, cannot register replica"
            )

        if old_service.find_replica(replica_id) is not None:
            # NOTE: as of 0.19.25, the dstack server relies on the exact text of this error.
            # See dstack._internal.server.services.services.register_replica
            raise ProxyError(f"Replica {replica_id} already exists in service {old_service.fmt()}")

        service = old_service.with_replicas(old_service.replicas + (replica,))

        logger.debug("Registering replica %s in service %s", replica.id, service.fmt())
        failures = await apply_service(
            service=service,
            old_service=old_service,
            repo=repo,
            nginx=nginx,
            service_conn_pool=service_conn_pool,
        )
        if replica in failures:
            raise ProxyError(
                f"Cannot register replica {replica.id}"
                f" in service {service.fmt()}: {failures[replica]}"
            )
        await repo.set_service(service)

    logger.info("Replica %s in service %s is registered now", replica.id, service.fmt())


async def unregister_replica(
    project_name: str,
    run_name: str,
    replica_id: str,
    repo: GatewayProxyRepo,
    nginx: Nginx,
    service_conn_pool: ServiceConnectionPool,
) -> None:
    async with lock:
        old_service = await repo.get_service(project_name, run_name)
        if old_service is None:
            raise ProxyError(
                f"Service {project_name}/{run_name} does not exist, cannot unregister replica"
            )

        replica = old_service.find_replica(replica_id)
        if replica is None:
            raise ProxyError(
                f"Replica {replica_id} does not exist in service {old_service.fmt()},"
                " cannot unregister"
            )

        service = old_service.with_replicas(tuple(r for r in old_service.replicas if r != replica))

        logger.debug("Unregistering replica %s in service %s", replica.id, service.fmt())

        await apply_service(
            service=service,
            old_service=old_service,
            repo=repo,
            nginx=nginx,
            service_conn_pool=service_conn_pool,
        )
        await repo.set_service(service)

    logger.info("Replica %s in service %s is unregistered now", replica_id, service.fmt())


async def register_model_entrypoint(
    project_name: str,
    domain: str,
    https: bool,
    repo: GatewayProxyRepo,
    nginx: Nginx,
) -> None:
    entrypoint = gateway_models.ModelEntrypoint(
        project_name=project_name,
        domain=domain,
        https=https,
    )
    logger.debug("Registering entrypoint %s in project %s", domain, project_name)
    await apply_entrypoint(entrypoint, repo, nginx)
    await repo.set_entrypoint(entrypoint)
    logger.info("Entrypoint %s is now registered in project %s", domain, project_name)


async def apply_service(
    service: models.Service,
    old_service: Optional[models.Service],
    repo: GatewayProxyRepo,
    nginx: Nginx,
    service_conn_pool: ServiceConnectionPool,
) -> dict[models.Replica, BaseException]:
    if old_service is not None:
        if service.domain != old_service.domain:
            raise UnexpectedProxyError(
                f"Did not expect service {service.fmt()}"
                f" domain name to change ({old_service.domain} -> {service.domain})"
            )
        await stop_replica_connections(
            ids=(
                replica.id for replica in old_service.replicas if replica not in service.replicas
            ),
            service_conn_pool=service_conn_pool,
        )
    replica_conns, replica_failures = await get_or_add_replica_connections(
        service, repo, service_conn_pool
    )
    replica_configs = [
        ReplicaConfig(id=replica.id, socket=conn.app_socket_path)
        for replica, conn in replica_conns.items()
    ]
    service_config = await get_nginx_service_config(service, replica_configs)
    await nginx.register(service_config, (await repo.get_config()).acme_settings)
    return replica_failures


async def get_or_add_replica_connections(
    service: models.Service, repo: BaseProxyRepo, service_conn_pool: ServiceConnectionPool
) -> tuple[dict[models.Replica, ServiceConnection], dict[models.Replica, BaseException]]:
    project = await repo.get_project(service.project_name)
    if project is None:
        raise UnexpectedProxyError(
            f"Project {service.project_name} unexpectedly missing, even though service"
            f" {service.fmt()} exists."
        )
    replica_conns, replica_failures = {}, {}
    tasks = [
        service_conn_pool.get_or_add(project, service, replica) for replica in service.replicas
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for replica, conn_or_err in zip(service.replicas, results):
        if isinstance(conn_or_err, BaseException):
            replica_failures[replica] = conn_or_err
            logger.warning(
                "Failed starting connection to replica %s in service %s: %s",
                replica.id,
                service.fmt(),
                conn_or_err,
            )
        else:
            replica_conns[replica] = conn_or_err
    return replica_conns, replica_failures


async def stop_replica_connections(
    ids: Iterable[str], service_conn_pool: ServiceConnectionPool
) -> None:
    tasks = map(service_conn_pool.remove, ids)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for replica_id, exc in zip(ids, results):
        if isinstance(exc, Exception):
            logger.error("Error stopping connection to replica %s: %s", replica_id, exc)


async def get_nginx_service_config(
    service: models.Service, replicas: Iterable[ReplicaConfig]
) -> ServiceConfig:
    limit_req_zones: list[LimitReqZoneConfig] = []
    locations: list[LocationConfig] = []
    for i, rate_limit in enumerate(service.rate_limits):
        zone_name = f"{i}.{service.domain_safe}"
        if isinstance(rate_limit.key, models.IPAddressPartitioningKey):
            key = "$binary_remote_addr"
        elif isinstance(rate_limit.key, models.HeaderPartitioningKey):
            key = f"$http_{rate_limit.key.header.lower().replace('-', '_')}"
        else:
            raise TypeError(f"Unexpected key type {type(rate_limit.key)}")
        limit_req_zones.append(
            LimitReqZoneConfig(name=zone_name, key=key, rpm=round(rate_limit.rps * 60))
        )
        locations.append(
            LocationConfig(
                prefix=rate_limit.prefix,
                limit_req=LimitReqConfig(zone=zone_name, burst=rate_limit.burst),
            )
        )
    if not any(location.prefix == "/" for location in locations):
        locations.append(LocationConfig(prefix="/", limit_req=None))
    return ServiceConfig(
        domain=service.domain_safe,
        https=service.https_safe,
        project_name=service.project_name,
        auth=service.auth,
        client_max_body_size=service.client_max_body_size,
        access_log_path=ACCESS_LOG_PATH,
        limit_req_zones=limit_req_zones,
        locations=locations,
        replicas=sorted(replicas, key=lambda r: r.id),  # sort for reproducible configs
    )


async def apply_entrypoint(
    entrypoint: gateway_models.ModelEntrypoint, repo: GatewayProxyRepo, nginx: Nginx
) -> None:
    config = ModelEntrypointConfig(
        domain=entrypoint.domain,
        https=entrypoint.https,
        project_name=entrypoint.project_name,
    )
    acme = (await repo.get_config()).acme_settings
    await nginx.register(config, acme)


async def apply_all(
    repo: GatewayProxyRepo, nginx: Nginx, service_conn_pool: ServiceConnectionPool
) -> None:
    service_tasks = [
        apply_service(
            service=service,
            old_service=None,
            repo=repo,
            nginx=nginx,
            service_conn_pool=service_conn_pool,
        )
        for service in await repo.list_services()
    ]
    entrypoint_tasks = [
        apply_entrypoint(entrypoint, repo, nginx) for entrypoint in await repo.list_entrypoints()
    ]
    results = await asyncio.gather(*service_tasks, *entrypoint_tasks, return_exceptions=True)
    for exc in results:
        if isinstance(exc, Exception):
            logger.error("Exception restoring gateway: %s", exc)


def model_schema_to_format_spec(model: schemas.AnyModel) -> models.AnyModelFormat:
    if model.type == "chat":
        if model.format == "openai":
            return models.OpenAIChatModelFormat(prefix=model.prefix)
        elif model.format == "tgi":
            return models.TGIChatModelFormat(
                chat_template=model.chat_template,
                eos_token=model.eos_token,
            )
        else:
            raise UnexpectedProxyError(f"Unexpected model format {model.format}")
    else:
        raise UnexpectedProxyError(f"Unexpected model type {model.type}")
