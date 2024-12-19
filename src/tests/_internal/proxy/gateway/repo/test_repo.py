from pathlib import Path

import pytest

from dstack._internal.proxy.gateway.models import ACMESettings, GlobalProxyConfig, ModelEntrypoint
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.lib.testing.common import make_project, make_service
from tests._internal.proxy.lib.routers.test_model_proxy import make_model


@pytest.mark.asyncio
async def test_persist_repo(tmp_path: Path) -> None:
    proj_1 = make_project("proj-1")
    proj_2 = make_project("proj-2")
    srv_1 = make_service("proj-1", "run-1", domain="run-1.gtw.test")
    srv_2 = make_service("proj-2", "run-2", domain="run-2.gtw.test")
    model_1 = make_model("proj-1", "model-1", run_name="run-1")
    entrypoint_1 = ModelEntrypoint(project_name="proj-1", domain="gateway.gtw.test", https=True)
    config = GlobalProxyConfig(acme_settings=ACMESettings(server="https://acme.test"))
    file = tmp_path / "state-v2.json"

    repo = GatewayProxyRepo.load(file)
    await repo.set_config(config)
    await repo.set_project(proj_1)
    await repo.set_project(proj_2)
    await repo.set_entrypoint(entrypoint_1)
    await repo.set_service(srv_1)
    await repo.set_service(srv_2)
    await repo.set_model(model_1)

    repo = GatewayProxyRepo.load(file)  # reload from file
    assert await repo.get_config() == config
    assert await repo.get_project("proj-1") == proj_1
    assert await repo.get_project("proj-2") == proj_2
    assert await repo.list_entrypoints() == [entrypoint_1]
    assert set(await repo.list_services()) == {srv_1, srv_2}
    assert await repo.list_models("proj-1") == [model_1]
