from typing import Dict, Optional
from unittest.mock import Mock, patch

import pytest
from dstack.gateway.openai.store import OpenAIStore
from dstack.gateway.schemas import Service
from dstack.gateway.services.nginx import Nginx
from dstack.gateway.services.store import Store


@pytest.fixture()
def ssh_tunnel():
    with patch("dstack.gateway.services.store.SSHTunnel.create") as mock:
        yield mock.return_value


@pytest.fixture()
def nginx():
    yield Mock(Nginx)


class TestRegister:
    @pytest.mark.asyncio
    async def test_fail_tunnel(self, ssh_tunnel, nginx):
        store = Store(nginx=nginx)
        ssh_tunnel.start.side_effect = FooException()
        with pytest.raises(FooException):
            await store.register("project", get_service("domain.com"))
        ssh_tunnel.start.assert_called_once()
        assert not ssh_tunnel.stop.called
        assert not nginx.register_service.called
        assert not nginx.unregister_domain.called

    @pytest.mark.asyncio
    async def test_fail_nginx(self, ssh_tunnel, nginx):
        store = Store(nginx=nginx)
        nginx.register_service.side_effect = FooException()
        with pytest.raises(FooException):
            await store.register("project", get_service("domain.com"))
        ssh_tunnel.start.assert_called_once()
        ssh_tunnel.stop.assert_called_once()
        nginx.register_service.assert_called_once()
        assert not nginx.unregister_domain.called

    @pytest.mark.asyncio
    async def test_fail_rollback(self, ssh_tunnel, nginx):
        store = Store(nginx=nginx)
        nginx.register_service.side_effect = FooException()
        ssh_tunnel.stop.side_effect = BarException()
        with pytest.raises(FooException):
            await store.register("project", get_service("domain.com"))
        ssh_tunnel.start.assert_called_once()
        ssh_tunnel.stop.assert_called_once()
        nginx.register_service.assert_called_once()
        assert not nginx.unregister_domain.called

    @pytest.mark.asyncio
    async def test_fail_subscriber(self, ssh_tunnel, nginx):
        store = Store(nginx=nginx)
        openai_store = Mock(OpenAIStore)
        await store.subscribe(openai_store)
        openai_store.on_register.side_effect = FooException()
        with pytest.raises(FooException):
            await store.register("project", get_service("domain.com", {"openai": {}}))
        ssh_tunnel.start.assert_called_once()
        ssh_tunnel.stop.assert_called_once()
        nginx.register_service.assert_called_once()
        nginx.unregister_domain.assert_called_once()


def get_service(domain: str, options: Optional[Dict] = None) -> Service:
    return Service(
        public_domain=domain,
        app_port=8000,
        ssh_host="user@host",
        ssh_port=22,
        options=options or {},
    )


class FooException(Exception):
    pass


class BarException(Exception):
    pass
