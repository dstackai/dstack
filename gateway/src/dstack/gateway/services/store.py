import asyncio
import functools
import logging
from abc import ABC, abstractmethod
from asyncio import Lock
from collections import defaultdict
from contextlib import AsyncExitStack
from functools import lru_cache, partial
from typing import Dict, List, Set, Tuple

from dstack.gateway.common import run_async
from dstack.gateway.errors import GatewayError
from dstack.gateway.schemas import Service
from dstack.gateway.services.nginx import Nginx, get_nginx
from dstack.gateway.services.tunnel import SSHTunnel

logger = logging.getLogger(__name__)


class Store:
    def __init__(self, nginx: Nginx):
        self.services: Dict[str, Tuple[Service, SSHTunnel]] = {}
        self.projects: Dict[str, Set[str]] = defaultdict(set)
        self.entrypoints: Dict[str, Tuple[str, str]] = {}
        self.nginx = nginx
        self.lock = Lock()
        self.subscribers: List["StoreSubscriber"] = []

    async def register(self, project: str, service: Service):
        async with self.lock:
            if service.public_domain in self.services:
                raise GatewayError(f"Domain {service.public_domain} is already registered")
            logger.info("%s: registering service %s", project, service.public_domain)

            tunnel = SSHTunnel(
                host=service.ssh_host,
                port=service.ssh_port,
                app_port=service.app_port,
                docker_host=service.docker_ssh_host,
                docker_port=service.docker_ssh_port,
            )
            async with AsyncExitStack() as stack:
                await run_async(tunnel.start)
                stack.push_async_callback(supress_exc(run_async, tunnel.stop))

                await self.nginx.register_service(service.public_domain, tunnel.sock_path)
                stack.push_async_callback(
                    supress_exc(self.nginx.unregister_domain, service.public_domain)
                )

                for subscriber in self.subscribers:
                    await subscriber.on_register(project, service)
                    stack.push_async_callback(
                        supress_exc(subscriber.on_unregister, project, service.public_domain)
                    )

                stack.pop_all()  # no need to rollback
            self.projects[project].add(service.public_domain)
            self.services[service.public_domain] = (service, tunnel)

    async def register_entrypoint(self, project: str, domain: str, module: str):
        async with self.lock:
            if domain in self.entrypoints:
                if self.entrypoints[domain] == (project, module):
                    return
                raise GatewayError(f"Domain {domain} is already registered")

            logger.info("%s: registering entrypoint %s", project, domain)
            await self.nginx.register_entrypoint(domain, f"/api/{module}/{project}")
            self.entrypoints[domain] = (project, module)

    async def unregister_all(self):
        async with self.lock:
            logger.info("Unregistering all services")
            stop_tunnels = [run_async(tunnel.stop) for _, tunnel in self.services.values()]
            unregister_services = [
                self.nginx.unregister_domain(domain) for domain in self.services.keys()
            ]
            on_unregister = [
                subscriber.on_unregister(project, domain)
                for subscriber in self.subscribers
                for project, domains in self.projects.items()
                for domain in domains
            ]
            await asyncio.gather(
                *stop_tunnels, *unregister_services, *on_unregister, return_exceptions=True
            )
            self.services.clear()

    async def unregister(self, project: str, domain: str):
        async with self.lock:
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
                *(subscriber.on_unregister(project, domain) for subscriber in self.subscribers),
                return_exceptions=True,
            )

    async def list_services(self, project: str) -> List:
        services = []
        async with self.lock:
            for domain in self.projects.get(project, []):
                service, _ = self.services[domain]
                services.append(service)
        return services

    async def subscribe(self, subscriber: "StoreSubscriber"):
        async with self.lock:
            self.subscribers.append(subscriber)


class StoreSubscriber(ABC):
    @abstractmethod
    async def on_register(self, project: str, service: Service):
        ...

    @abstractmethod
    async def on_unregister(self, project: str, domain: str):
        ...


def supress_exc(func, *args, **kwargs):
    @functools.wraps(func)
    async def wrapper():
        try:
            return await func(*args, **kwargs)
        except Exception:
            pass

    return wrapper


@lru_cache()
def get_store() -> Store:
    return Store(nginx=get_nginx())
