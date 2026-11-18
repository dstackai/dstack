from pathlib import Path

import pytest
from pydantic import AnyHttpUrl

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
    config = GlobalProxyConfig(acme_settings=ACMESettings(server=AnyHttpUrl("https://acme.test")))
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
    assert sorted(await repo.list_services(), key=lambda s: (s.project_name, s.run_name)) == [
        srv_1,
        srv_2,
    ]
    assert await repo.list_models("proj-1") == [model_1]


@pytest.mark.asyncio
class TestSetServices:
    async def test_failed_replace_preserves_state_and_retries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_file = tmp_path / "state.json"
        repo = GatewayProxyRepo.load(state_file)
        old_service = make_service("project", "run")
        new_service = old_service.model_copy(update={"auth": not old_service.auth})
        await repo.set_services([old_service])
        previous_content = state_file.read_bytes()

        def fail_replace(source: Path, target: Path) -> None:
            # The replacement is complete, but cannot be installed over the saved state.
            assert source.read_bytes() != previous_content
            raise OSError("state replacement failed")

        with monkeypatch.context() as scoped:
            scoped.setattr(Path, "replace", fail_replace)
            with pytest.raises(OSError, match="state replacement failed"):
                await repo.set_services([new_service])

        assert await repo.get_service("project", "run") == old_service
        assert state_file.read_bytes() == previous_content
        assert await GatewayProxyRepo.load(state_file).get_service("project", "run") == old_service
        assert list(tmp_path.iterdir()) == [state_file]

        await repo.set_services([new_service])
        assert await repo.get_service("project", "run") == new_service
        assert await GatewayProxyRepo.load(state_file).get_service("project", "run") == new_service
