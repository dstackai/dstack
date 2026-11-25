from pathlib import Path

import pytest
from pydantic import AnyHttpUrl

from dstack._internal.proxy.gateway.models import (
    ACMESettings,
    GlobalProxyConfig,
    ImportedModel,
    ModelEntrypoint,
)
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.lib.testing.common import make_project, make_service
from tests._internal.proxy.lib.routers.test_model_proxy import TGI_FORMAT, make_model


def make_import(
    export_id: str = "export-1", exporter_project: str = "exporter-proj"
) -> ImportedModel:
    return ImportedModel(
        importer_project="importer-proj",
        export_id=export_id,
        exporter_project=exporter_project,
        name="test-model",
    )


@pytest.mark.asyncio
async def test_persist_repo(tmp_path: Path) -> None:
    proj_1 = make_project("proj-1")
    proj_2 = make_project("proj-2")
    srv_1 = make_service("proj-1", "run-1", domain="run-1.gtw.test")
    srv_2 = make_service("proj-2", "run-2", domain="run-2.gtw.test")
    model_1 = make_model("proj-1", "model-1", run_name="run-1")
    import_1 = make_import()
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
    await repo.set_import(import_1)

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
    assert await repo.list_imports() == [import_1]


@pytest.mark.asyncio
class TestImports:
    async def test_importer_project_gets_model_of_exporter_project(self) -> None:
        repo = GatewayProxyRepo()
        model = make_model("exporter-proj", "test-model", run_name="run-1")
        await repo.set_model(model)
        await repo.set_import(make_import())

        imported_model = model.model_copy(update={"export_id": "export-1"})
        assert await repo.list_models("importer-proj") == [imported_model]
        assert await repo.list_models("Importer-Proj") == [imported_model]
        assert await repo.get_model("Importer-Proj", "test-model") == imported_model
        assert await repo.get_model("exporter-proj", "test-model") == model
        assert await repo.list_models("other-proj") == []

        await repo.delete_import("importer-proj", "export-1", "test-model")
        assert await repo.list_models("importer-proj") == []
        assert await repo.get_model("importer-proj", "test-model") is None

    async def test_import_follows_model_to_another_service(self) -> None:
        repo = GatewayProxyRepo()
        await repo.set_import(make_import())
        # No service of the exporter project has registered the model yet.
        assert await repo.list_models("importer-proj") == []
        assert await repo.get_model("importer-proj", "test-model") is None

        await repo.set_model(make_model("exporter-proj", "test-model", run_name="run-1"))
        model = await repo.get_model("importer-proj", "test-model")
        assert model is not None
        assert model.run_name == "run-1"

        # Another service registers the model, and the first service is unregistered.
        await repo.set_model(make_model("exporter-proj", "test-model", run_name="run-2"))
        await repo.delete_models_by_run("exporter-proj", "run-1")
        model = await repo.get_model("importer-proj", "test-model")
        assert model is not None
        assert (model.project_name, model.run_name) == ("exporter-proj", "run-2")
        assert model.export_id == "export-1"

        # Requests to models with the `tgi` format are not metered.
        await repo.set_model(
            make_model("exporter-proj", "test-model", run_name="run-3", format_spec=TGI_FORMAT)
        )
        assert await repo.list_models("importer-proj") == []
        assert await repo.get_model("importer-proj", "test-model") is None

    async def test_own_model_wins_over_import_with_same_name(self) -> None:
        repo = GatewayProxyRepo()
        own_model = make_model("importer-proj", "test-model", run_name="own-run")
        await repo.set_model(own_model)
        await repo.set_model(make_model("exporter-proj", "test-model", run_name="run-1"))
        await repo.set_import(make_import())
        assert await repo.list_models("importer-proj") == [own_model]
        assert await repo.get_model("importer-proj", "test-model") == own_model

        await repo.delete_models_by_run("importer-proj", "own-run")
        [model] = await repo.list_models("importer-proj")
        assert model.export_id == "export-1"

    async def test_keeps_one_import_per_project_and_model_name(self) -> None:
        repo = GatewayProxyRepo()
        await repo.set_model(make_model("exporter-proj", "test-model", run_name="run-1"))
        await repo.set_model(make_model("exporter-proj-2", "test-model", run_name="run-2"))
        await repo.set_import(make_import("export-1", "exporter-proj"))
        # The import of the model through another export replaces it.
        new_import = make_import("export-2", "exporter-proj-2")
        await repo.set_import(new_import)
        assert await repo.list_imports() == [new_import]
        model = await repo.get_model("importer-proj", "test-model")
        assert model is not None
        assert (model.project_name, model.export_id) == ("exporter-proj-2", "export-2")

        # Deleting the import through the previous export changes nothing.
        await repo.delete_import("importer-proj", "export-1", "test-model")
        assert await repo.list_imports() == [new_import]
        await repo.delete_import("importer-proj", "export-2", "test-model")
        assert await repo.list_imports() == []


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
