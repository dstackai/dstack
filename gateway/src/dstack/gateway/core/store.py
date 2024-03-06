import asyncio
import concurrent
import functools
import logging
import os
from abc import ABC, abstractmethod
from asyncio import CancelledError, Lock
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack
from functools import lru_cache
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field, PrivateAttr, ValidationError

from dstack.gateway.common import run_async
from dstack.gateway.core.nginx import Nginx
from dstack.gateway.core.persistent import get_persistent_state
from dstack.gateway.core.tunnel import SSHTunnel
from dstack.gateway.errors import GatewayError

logger = logging.getLogger(__name__)


class Replica(BaseModel):
    id: str
    app_port: int
    ssh_host: str
    ssh_port: int
    ssh_jump_host: Optional[str]
    ssh_jump_port: Optional[int]
    ssh_tunnel: Optional[SSHTunnel] = None


class Service(BaseModel):
    id: str
    domain: str
    auth: bool
    options: dict
    replicas: List[Replica] = []


class Store(BaseModel):
    """
    Store is a central place to register and unregister services.
    Other components can subscribe to updates.
    Its internal state could be serialized to a file and restored from it using pydantic.
    """

    services: Dict[str, Service] = {}
    projects: DefaultDict[str, Set[str]] = defaultdict(set)
    entrypoints: Dict[str, Tuple[str, str]] = {}
    nginx: Nginx = Field(default_factory=Nginx)
    _lock: Lock = Lock()
    _subscribers: List["StoreSubscriber"] = []
    _ssh_keys_dir = PrivateAttr(
        default_factory=lambda: Path("~/.ssh/projects").expanduser().resolve()
    )

    async def register_service(self, project: str, service: Service, ssh_private_key: str):
        async with self._lock:
            if service.id in self.services:
                raise GatewayError(f"Service ID {service.id!r} is already registered")
            if service.replicas:
                raise GatewayError("Not implemented: replicas should be registered separately")

            logger.debug("%s: registering service %s (%s)", project, service.id, service.domain)

            # Save project SSH key
            self._ssh_keys_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            ssh_key_path = self._ssh_keys_dir / project
            if (
                ssh_key_path.exists()
                and ssh_key_path.read_text().strip() != ssh_private_key.strip()
            ):
                logger.warning(
                    "%s: SSH key for service %s (%s) is different from the previous one",
                    project,
                    service.id,
                    service.domain,
                )
            with open(
                ssh_key_path, "w", opener=lambda path, flags: os.open(path, flags, 0o600)
            ) as f:
                f.write(ssh_private_key)

            async with AsyncExitStack() as stack:
                # Configure nginx and issue SSL cert
                await self.nginx.register_service(
                    project,
                    service.id,
                    service.domain,
                    service.auth,
                )
                stack.push_async_callback(
                    supress_exc_async(self.nginx.unregister_domain, service.domain)
                )

                # Notify subscribers
                for subscriber in self._subscribers:
                    await subscriber.on_register(project, service)
                    stack.push_async_callback(
                        supress_exc_async(subscriber.on_unregister, project, service.id)
                    )

                # All fine, remove rollbacks
                stack.pop_all()

            self.services[service.id] = service
            self.projects[project].add(service.id)

        logger.info("%s: service %s (%s) is registered now", project, service.id, service.domain)

    async def unregister_service(self, project: str, service_id: str):
        async with self._lock:
            if service_id not in self.projects[project]:
                raise GatewayError(
                    f"Service ID {service_id!r} is not registered in project {project!r}"
                )
            service = self.services[service_id]

            logger.debug("%s: unregistering service %s (%s)", project, service_id, service.domain)

            await asyncio.gather(
                # Terminate all SSH tunnels
                *(
                    run_async(replica.ssh_tunnel.stop)
                    for replica in service.replicas
                    if replica.ssh_tunnel is not None
                ),
                # Unregister from nginx
                self.nginx.unregister_domain(service.domain),
                # Notify subscribers
                *(
                    subscriber.on_unregister(project, service.id)
                    for subscriber in self._subscribers
                ),
                return_exceptions=True,
            )

            self.projects[project].remove(service_id)
            self.services.pop(service_id)

        logger.info("%s: service %s (%s) is unregistered now", project, service_id, service.domain)

    async def register_replica(self, project: str, service_id: str, replica: Replica):
        async with self._lock:
            if service_id not in self.projects[project]:
                raise GatewayError(
                    f"Service ID {service_id!r} is not registered in project {project!r}"
                )
            if replica.ssh_tunnel:
                raise GatewayError("Not implemented: replica should not have a tunnel yet")
            service = self.services[service_id]

            logger.debug(
                "%s: registering replica %s for service %s (%s)",
                project,
                replica.id,
                service_id,
                service.domain,
            )

            async with AsyncExitStack() as stack:
                # Start SSH tunnel
                ssh_tunnel = SSHTunnel.create(
                    host=replica.ssh_host,
                    port=replica.ssh_port,
                    app_port=replica.app_port,
                    id_rsa_path=(self._ssh_keys_dir / project).as_posix(),
                    jump_host=replica.ssh_jump_host,
                    jump_port=replica.ssh_jump_port,
                )
                await run_async(ssh_tunnel.start)
                stack.push_async_callback(supress_exc_async(run_async, ssh_tunnel.stop))

                # Add to nginx
                await self.nginx.add_upstream(
                    service.domain, f"unix:{ssh_tunnel.sock_path}", replica.id
                )
                stack.push_async_callback(
                    supress_exc_async(self.nginx.remove_upstream, service.domain, replica.id)
                )

                # All fine, remove rollbacks
                stack.pop_all()

            replica.ssh_tunnel = ssh_tunnel
            service.replicas.append(replica)

        logger.info(
            "%s: replica %s for service %s (%s) is registered now",
            project,
            replica.id,
            service_id,
            service.domain,
        )

    async def unregister_replica(self, project: str, service_id: str, replica_id: str):
        async with self._lock:
            if service_id not in self.projects[project]:
                raise GatewayError(
                    f"Service ID {service_id!r} is not registered in project {project!r}"
                )
            service = self.services[service_id]

            for replica in service.replicas:
                if replica.id == replica_id:
                    break
            else:
                raise GatewayError(
                    f"Replica ID {replica_id!r} is not registered in service {service_id!r}"
                )

            logger.debug(
                "%s: unregistering replica %s for service %s (%s)",
                project,
                replica_id,
                service_id,
                service.domain,
            )

            await asyncio.gather(
                # Terminate SSH tunnel
                run_async(replica.ssh_tunnel.stop),
                # Remove from nginx
                self.nginx.remove_upstream(service.domain, replica.id),
                return_exceptions=True,
            )

            service.replicas.remove(replica)

        logger.info(
            "%s: replica %s for service %s (%s) is unregistered now",
            project,
            replica_id,
            service_id,
            service.domain,
        )

    async def register_entrypoint(self, project: str, domain: str, module: str):
        async with self._lock:
            if domain in self.entrypoints:
                if self.entrypoints[domain] == (project, module):
                    return
                raise GatewayError(
                    f"Domain {domain} is already registered as {self.entrypoints[domain]}"
                )

            logger.debug("%s: registering entrypoint %s for module %s", project, domain, module)

            await self.nginx.register_entrypoint(domain, f"/api/{module}/{project}")
            self.entrypoints[domain] = (project, module)

        logger.info("%s: entrypoint %s is now registered", project, domain)

    async def subscribe(self, subscriber: "StoreSubscriber"):
        async with self._lock:
            self._subscribers.append(subscriber)

    def start_tunnels(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(supress_exc(replica.ssh_tunnel.start))
                for service_id, service in self.services.items()
                for replica in service.replicas
                if replica.ssh_tunnel is not None
            ]
            concurrent.futures.wait(futures)


class StoreSubscriber(ABC):
    @abstractmethod
    async def on_register(self, project: str, service: Service):
        ...

    @abstractmethod
    async def on_unregister(self, project: str, service_id: str):
        ...


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


@lru_cache()
def get_store() -> Store:
    try:
        store = Store.model_validate(get_persistent_state().get("store", {}))
    except ValidationError as e:
        logger.warning("Failed to load store state: %s", e)
        store = Store()
    # Start tunnels after restoring the state
    store.start_tunnels()
    return store
