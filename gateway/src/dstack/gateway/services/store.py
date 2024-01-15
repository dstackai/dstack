import asyncio
import concurrent
import functools
import logging
import os
from abc import ABC, abstractmethod
from asyncio import Lock
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack
from functools import lru_cache
from pathlib import Path
from typing import DefaultDict, Dict, List, Set, Tuple

from pydantic import BaseModel, Field, PrivateAttr

from dstack.gateway.common import run_async
from dstack.gateway.errors import GatewayError
from dstack.gateway.schemas import Service
from dstack.gateway.services.nginx import Nginx
from dstack.gateway.services.persistent import get_persistent_state
from dstack.gateway.services.tunnel import SSHTunnel

logger = logging.getLogger(__name__)


class Store(BaseModel):
    """
    Store is a central place to register and unregister services.
    Other components can subscribe to updates.
    Its internal state could be serialized to a file and restored from it using pydantic.
    """

    services: Dict[str, Tuple[Service, SSHTunnel]] = {}
    projects: DefaultDict[str, Set[str]] = defaultdict(set)
    entrypoints: Dict[str, Tuple[str, str]] = {}
    nginx: Nginx = Field(default_factory=Nginx)
    _lock: Lock = Lock()
    _subscribers: List["StoreSubscriber"] = []
    _ssh_keys_dir = PrivateAttr(
        default_factory=lambda: Path("~/.ssh/projects").expanduser().resolve()
    )

    async def register(self, project: str, service: Service):
        async with self._lock:
            if service.public_domain in self.services:
                raise GatewayError(f"Domain {service.public_domain} is already registered")
            logger.info("%s: registering service %s", project, service.public_domain)

            tunnel = SSHTunnel.create(
                host=service.ssh_host,
                port=service.ssh_port,
                app_port=service.app_port,
                id_rsa_path=(self._ssh_keys_dir / project).as_posix(),
                docker_host=service.docker_ssh_host,
                docker_port=service.docker_ssh_port,
            )
            async with AsyncExitStack() as stack:
                await run_async(tunnel.start)
                stack.push_async_callback(supress_exc_async(run_async, tunnel.stop))

                await self.nginx.register_service(service.public_domain, tunnel.sock_path)
                stack.push_async_callback(
                    supress_exc_async(self.nginx.unregister_domain, service.public_domain)
                )

                for subscriber in self._subscribers:
                    await subscriber.on_register(project, service)
                    stack.push_async_callback(
                        supress_exc_async(subscriber.on_unregister, project, service.public_domain)
                    )

                stack.pop_all()  # no need to rollback
            self.projects[project].add(service.public_domain)
            self.services[service.public_domain] = (service, tunnel)

    async def register_entrypoint(self, project: str, domain: str, module: str):
        async with self._lock:
            if domain in self.entrypoints:
                if self.entrypoints[domain] == (project, module):
                    return
                raise GatewayError(f"Domain {domain} is already registered")

            logger.info("%s: registering entrypoint %s", project, domain)
            await self.nginx.register_entrypoint(domain, f"/api/{module}/{project}")
            self.entrypoints[domain] = (project, module)

    async def unregister(self, project: str, domain: str):
        async with self._lock:
            if domain not in self.services:
                raise GatewayError(f"Domain {domain} is not registered")
            if domain not in self.projects[project]:
                raise GatewayError(f"Domain {domain} is not registered in project {project}")
            logger.info("%s: unregistering service %s", project, domain)

            self.projects[project].remove(domain)
            service, tunnel = self.services.pop(domain)
            await asyncio.gather(
                run_async(tunnel.stop),
                self.nginx.unregister_domain(domain),
                *(subscriber.on_unregister(project, domain) for subscriber in self._subscribers),
                return_exceptions=True,
            )

    async def subscribe(self, subscriber: "StoreSubscriber"):
        async with self._lock:
            self._subscribers.append(subscriber)

    async def preflight(self, project: str, domain: str, ssh_private_key: str):
        async with self._lock:
            if domain in self.services:
                raise GatewayError(f"Domain {domain} is already registered")
            logger.info("%s: preflighting service %s", project, domain)

            await run_async(self.nginx.run_certbot, domain)

            self._ssh_keys_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            ssh_key_path = self._ssh_keys_dir / project
            if (
                ssh_key_path.exists()
                and ssh_key_path.read_text().strip() != ssh_private_key.strip()
            ):
                logger.warning("%s: SSH key for project %s is different", domain, project)
            with open(
                ssh_key_path, "w", opener=lambda path, flags: os.open(path, flags, 0o600)
            ) as f:
                f.write(ssh_private_key)

    def start_tunnels(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(supress_exc(tunnel.start))
                for domain, (service, tunnel) in self.services.items()
            ]
            concurrent.futures.wait(futures)


class StoreSubscriber(ABC):
    @abstractmethod
    async def on_register(self, project: str, service: Service):
        ...

    @abstractmethod
    async def on_unregister(self, project: str, domain: str):
        ...


def supress_exc_async(func, *args, **kwargs):
    @functools.wraps(func)
    async def wrapper():
        try:
            return await func(*args, **kwargs)
        except Exception:
            pass

    return wrapper


def supress_exc(func, *args, **kwargs):
    @functools.wraps(func)
    def wrapper():
        try:
            return func(*args, **kwargs)
        except Exception:
            pass

    return wrapper


@lru_cache()
def get_store() -> Store:
    store = Store.model_validate(get_persistent_state().get("store", {}))
    store.start_tunnels()  # start tunnels after restoring the state
    return store
