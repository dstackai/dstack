from pathlib import Path

import pytest
import yaml

from dstack._internal.cli.services.endpoint_presets import EndpointPresetStore
from dstack._internal.core.errors import CLIError
from tests._internal.cli.endpoint_presets import get_endpoint_preset_recipe

pytestmark = pytest.mark.windows


class TestEndpointPresetStore:
    def test_saves_and_lists_self_contained_recipe(self, tmp_path: Path):
        store = EndpointPresetStore(tmp_path / "presets")
        recipe = get_endpoint_preset_recipe()

        path = store.save(recipe)

        assert path == (tmp_path / "presets" / "models--Qwen--Qwen3.5-27B" / "8f3a12c4.yaml")
        data = yaml.safe_load(path.read_text())
        assert data["base"] == recipe.base
        assert data["id"] == recipe.id
        assert data["model"] == recipe.model
        assert "recipes" not in data
        assert store.list() == [recipe]
        assert store.get(recipe.id) == recipe
        assert not list(path.parent.glob("*.tmp"))

    def test_replaces_same_recipe_id_atomically(self, tmp_path: Path):
        store = EndpointPresetStore(tmp_path / "presets")
        recipe = get_endpoint_preset_recipe()
        store.save(recipe)

        updated = recipe.copy(update={"context_length": 16384})
        store.save(updated)

        assert store.get(updated.id) == updated

    def test_rejects_duplicate_recipe_id(self, tmp_path: Path):
        store = EndpointPresetStore(tmp_path / "presets")
        recipe = get_endpoint_preset_recipe()
        store.save(recipe)
        store.save(recipe.copy(update={"base": "Qwen/Another-Model"}))

        with pytest.raises(CLIError, match="is not unique"):
            store.get(recipe.id)

    def test_rejects_recipe_without_successful_benchmark(self, tmp_path: Path):
        store = EndpointPresetStore(tmp_path / "presets")
        path = store.save(get_endpoint_preset_recipe())
        data = yaml.safe_load(path.read_text())
        data["validations"][0]["benchmarks"] = []
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        with pytest.raises(CLIError, match="successful benchmark"):
            store.list()
