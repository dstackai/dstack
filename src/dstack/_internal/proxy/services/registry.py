import asyncio
import concurrent
import functools
from asyncio import CancelledError, Lock
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import AnyHttpUrl

import dstack._internal.proxy.schemas.registry as schemas
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.proxy.errors import ProxyError, UnexpectedProxyError
from dstack._internal.proxy.repos import models
from dstack._internal.proxy.repos.base import BaseProxyRepo
from dstack._internal.proxy.repos.memory import InMemoryProxyRepo
from dstack._internal.proxy.services.nginx import (
    Nginx,
    ReplicaConfig,
    ServiceSiteConfig,
)
from dstack._internal.proxy.services.service_connection import service_replica_connection_pool
from dstack._internal.utils.logging import get_logger

ACCESS_LOG_PATH = Path("/var/log/nginx/dstack.access.log")
logger = get_logger(__name__)
lock = Lock()


# TODO: delete ~/.ssh/projects ?
# TODO: status codes for ProxyError


async def update_config(
    self,
    acme_server: Optional[AnyHttpUrl],
    acme_eab_kid: Optional[str],
    acme_eab_hmac_key: Optional[str],
) -> None:
    await self.nginx.set_acme_settings(acme_server, acme_eab_kid, acme_eab_hmac_key)


async def register_service(
    project_name: str,
    run_name: str,
    domain: str,
    https: bool,
    auth: bool,
    client_max_body_size: int,  # TODO
    model: Optional[schemas.AnyModel],
    ssh_private_key: str,
    repo: BaseProxyRepo,
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
            replicas=frozenset(),
        )

        await nginx.register(await get_nginx_service_config(service))
        await repo.set_service(service)

        if model is not None:
            await repo.set_model(
                project_name=project_name,
                model=models.ChatModel(
                    name=model.name,
                    created_at=datetime.now(),  # TODO
                    run_name=run_name,
                    format_spec=...,  # TODO
                ),
            )

    logger.info("Service %s/%s is registered now", project_name, run_name)


# TODO: depend on BaseProxyRepo or implement safe dependency on GatewayProxyRepo
async def unregister_service(
    project_name: str, run_name: str, repo: InMemoryProxyRepo, nginx: Nginx
) -> None:
    async with lock:
        service = await repo.get_service(project_name, run_name)
        if service is None:
            raise ProxyError(
                f"Service {project_name}/{run_name} is not registered, cannot unregister"
            )

        logger.debug("Unregistering service %s/%s", project_name, run_name)  # TODO

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
    repo: BaseProxyRepo,
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
            await nginx.register(await get_nginx_service_config(service))
            # TODO
            # stack.push_async_callback(
            #     supress_exc_async(nginx.remove_upstream, service.domain_safe, replica.id)
            # )

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
    project_name: str, run_name: str, replica_id: str, repo: BaseProxyRepo, nginx: Nginx
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
            nginx.register(await get_nginx_service_config(service)),
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


# async def register_entrypoint(self, project: str, domain: str, https: bool, module: str) -> None:
#     async with lock:
#         if domain in self.entrypoints:
#             if self.entrypoints[domain] == (project, module) and self.gateway_https == https:
#                 return
#             # If the gateway's https settings changed, re-register the endpoint.
#             elif self.entrypoints[domain] == (project, module) and self.gateway_https != https:
#                 await self.nginx.unregister_domain(domain)
#             else:
#                 raise GatewayError(
#                     f"Domain {domain} is already registered as {self.entrypoints[domain]}"
#                 )

#         logger.debug("%s: registering entrypoint %s for module %s", project, domain, module)

#         await self.nginx.register_entrypoint(domain, f"/api/{module}/{project}", https)
#         self.entrypoints[domain] = (project, module)
#         self.gateway_https = https

#     logger.info("%s: entrypoint %s is now registered", project, domain)


async def get_nginx_service_config(service: models.Service) -> ServiceSiteConfig:
    replicas = [await get_nginx_replica_config(replica) for replica in service.replicas]
    replicas.sort(key=lambda replica: replica.id)  # ensures reproducible configs
    return ServiceSiteConfig(
        domain=service.domain_safe,
        https=service.https_safe,
        project_name=service.project_name,
        run_name=service.run_name,
        auth=service.auth,
        client_max_body_size=1024 * 1024,  # TODO
        access_log_path=ACCESS_LOG_PATH,
        replicas=replicas,
    )


async def get_nginx_replica_config(replica: models.Replica) -> ReplicaConfig:
    conn = await service_replica_connection_pool.get(replica.id)
    if conn is None:
        raise UnexpectedProxyError(f"Connection to replica {replica.id} not found in pool")
    return ReplicaConfig(id=replica.id, socket=conn.app_socket_path)


def start_tunnels(self) -> None:
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(supress_exc(replica.ssh_tunnel.start))
            for service_id, service in self.services.items()
            for replica in service.replicas
            if replica.ssh_tunnel is not None
        ]
        concurrent.futures.wait(futures)


def supress_exc_async(func, *args, **kwargs):
    @functools.wraps(func)
    async def wrapper():
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if isinstance(e, CancelledError):
                raise

    return wrapper


def supress_exc(func, *args, **kwargs):
    @functools.wraps(func)
    def wrapper():
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if isinstance(e, CancelledError):
                raise

    return wrapper
