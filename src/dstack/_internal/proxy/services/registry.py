import asyncio
import functools
from asyncio import CancelledError, Lock
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import Optional

import dstack._internal.proxy.schemas.registry as schemas
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.proxy.errors import ProxyError, UnexpectedProxyError
from dstack._internal.proxy.repos import models
from dstack._internal.proxy.repos.gateway import GatewayProxyRepo
from dstack._internal.proxy.services.nginx import (
    ModelEntrypointConfig,
    Nginx,
    ReplicaConfig,
    ServiceConfig,
)
from dstack._internal.proxy.services.service_connection import service_replica_connection_pool
from dstack._internal.utils.logging import get_logger

ACCESS_LOG_PATH = Path("/var/log/nginx/dstack.access.log")
logger = get_logger(__name__)
lock = Lock()


async def register_service(
    project_name: str,
    run_name: str,
    domain: str,
    https: bool,
    auth: bool,
    client_max_body_size: int,
    model: Optional[schemas.AnyModel],
    ssh_private_key: str,
    repo: GatewayProxyRepo,
    nginx: Nginx,
) -> None:
    async with lock:
        if await repo.get_service(project_name, run_name) is not None:
            raise ProxyError(f"Service {project_name}/{run_name} is already registered")

        logger.debug("Registering service %s/%s", project_name, run_name)

        old_project = await repo.get_project(project_name)
        new_project = models.Project(name=project_name, ssh_private_key=ssh_private_key)
        if old_project is not None and old_project.ssh_private_key != new_project.ssh_private_key:
            logger.warning(
                "SSH key for service %s/%s is different from the previous one",
                project_name,
                run_name,
            )
        await repo.set_project(new_project)

        service = models.Service(
            project_name=project_name,
            run_name=run_name,
            domain=domain,
            https=https,
            auth=auth,
            client_max_body_size=client_max_body_size,
            replicas=frozenset(),
        )

        await nginx.register(
            await get_nginx_service_config(service), (await repo.get_config()).acme_settings
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

    logger.info("Service %s/%s is registered now", project_name, run_name)


async def unregister_service(
    project_name: str, run_name: str, repo: GatewayProxyRepo, nginx: Nginx
) -> None:
    async with lock:
        service = await repo.get_service(project_name, run_name)
        if service is None:
            raise ProxyError(
                f"Service {project_name}/{run_name} is not registered, cannot unregister"
            )

        logger.debug("Unregistering service %s/%s", project_name, run_name)

        results = await asyncio.gather(
            # Terminate all SSH tunnels
            *(service_replica_connection_pool.remove(replica.id) for replica in service.replicas),
            # Unregister from nginx
            nginx.unregister(service.domain_safe),
            return_exceptions=True,
        )
        for exc in results:
            if isinstance(exc, Exception):
                logger.error(
                    "Exception during unregistering service %s/%s: %s",
                    project_name,
                    run_name,
                    exc,
                )

        await repo.delete_models_by_run(project_name, run_name)
        await repo.delete_service(project_name, run_name)

    logger.info("Service %s/%s is unregistered now", project_name, run_name)


async def register_replica(
    project_name: str,
    run_name: str,
    replica_id: str,
    app_port: int,
    ssh_destination: str,
    ssh_port: int,
    ssh_proxy: Optional[SSHConnectionParams],
    repo: GatewayProxyRepo,
    nginx: Nginx,
) -> None:
    replica = models.Replica(
        id=replica_id,
        app_port=app_port,
        ssh_destination=ssh_destination,
        ssh_port=ssh_port,
        ssh_proxy=ssh_proxy,
    )

    async with lock:
        service = await repo.get_service(project_name, run_name)
        if service is None:
            raise ProxyError(
                f"Service {project_name}/{run_name} does not exist, cannot register replica"
            )

        service = models.Service(
            project_name=project_name,
            run_name=service.run_name,
            domain=service.domain,
            https=service.https,
            auth=service.auth,
            client_max_body_size=service.client_max_body_size,
            replicas=service.replicas | {replica},
        )

        project = await repo.get_project(project_name)
        if project is None:
            raise UnexpectedProxyError(f"Project {project_name!r} not found")

        logger.debug(
            "Registering replica %s for service %s/%s", replica.id, project_name, run_name
        )

        async with AsyncExitStack() as stack:
            # Start SSH tunnel
            await service_replica_connection_pool.add(project, service, replica)
            stack.push_async_callback(
                supress_exc_async(service_replica_connection_pool.remove, replica.id)
            )

            # Update Nginx config
            await nginx.register(
                await get_nginx_service_config(service), (await repo.get_config()).acme_settings
            )
            stack.push_async_callback(supress_exc_async(nginx.unregister, service.domain_safe))

            # All fine, remove rollbacks
            stack.pop_all()

        await repo.set_service(service)

    logger.info(
        "Replica %s for service %s/%s is registered now",
        replica.id,
        project_name,
        run_name,
    )


async def unregister_replica(
    project_name: str,
    run_name: str,
    replica_id: str,
    repo: GatewayProxyRepo,
    nginx: Nginx,
) -> None:
    async with lock:
        service = await repo.get_service(project_name, run_name)
        if service is None:
            raise ProxyError(
                f"Service {project_name}/{run_name} does not exist, cannot unregister replica"
            )

        replica = service.find_replica(replica_id)
        if replica is None:
            raise ProxyError(
                f"Replica {replica_id} does not exist in service {project_name}/{run_name},"
                " cannot unregister"
            )

        service = models.Service(
            project_name=project_name,
            run_name=service.run_name,
            domain=service.domain,
            https=service.https,
            auth=service.auth,
            client_max_body_size=service.client_max_body_size,
            replicas=service.replicas - {replica},
        )

        logger.debug(
            "Unregistering replica %s for service %s/%s",
            replica.id,
            project_name,
            service.run_name,
        )

        results = await asyncio.gather(
            # Terminate SSH tunnel
            service_replica_connection_pool.remove(replica.id),
            # Update Nginx config
            nginx.register(
                await get_nginx_service_config(service), (await repo.get_config()).acme_settings
            ),
            return_exceptions=True,
        )
        for exc in results:
            if isinstance(exc, Exception):
                logger.error(
                    "Exception during unregistering replica %s in service %s/%s: %s",
                    replica.id,
                    project_name,
                    service.run_name,
                    exc,
                )

        await repo.set_service(service)

    logger.info(
        "Replica %s in service %s/%s is unregistered now",
        replica_id,
        project_name,
        run_name,
    )


async def register_model_entrypoint(
    project_name: str,
    domain: str,
    https: bool,
    repo: GatewayProxyRepo,
    nginx: Nginx,
) -> None:
    config = ModelEntrypointConfig(
        domain=domain,
        https=https,
        project_name=project_name,
    )
    logger.debug("Registering entrypoint %s in project %s", domain, project_name)
    await nginx.register(config, (await repo.get_config()).acme_settings)
    logger.info("Entrypoint %s is now registered in project %s", domain, project_name)


async def get_nginx_service_config(service: models.Service) -> ServiceConfig:
    replicas = [await get_nginx_replica_config(replica) for replica in service.replicas]
    replicas.sort(key=lambda replica: replica.id)  # ensures reproducible configs
    return ServiceConfig(
        domain=service.domain_safe,
        https=service.https_safe,
        project_name=service.project_name,
        run_name=service.run_name,
        auth=service.auth,
        client_max_body_size=service.client_max_body_size,
        access_log_path=ACCESS_LOG_PATH,
        replicas=replicas,
    )


async def get_nginx_replica_config(replica: models.Replica) -> ReplicaConfig:
    conn = await service_replica_connection_pool.get(replica.id)
    if conn is None:
        raise UnexpectedProxyError(f"Connection to replica {replica.id} not found in pool")
    return ReplicaConfig(id=replica.id, socket=conn.app_socket_path)


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


def supress_exc_async(func, *args, **kwargs):
    @functools.wraps(func)
    async def wrapper():
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if isinstance(e, CancelledError):
                raise

    return wrapper
