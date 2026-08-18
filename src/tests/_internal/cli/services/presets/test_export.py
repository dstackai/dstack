from pathlib import Path

import pytest
import yaml

from dstack._internal.cli.services.presets.export import export_preset
from dstack._internal.cli.services.presets.store import PresetStore
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.files import FilePathMapping
from tests._internal.cli.common import get_preset

pytestmark = pytest.mark.windows


class TestExportPreset:
    def test_exports_a_deployable_service_configuration_with_its_files(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        preset.service.files = [
            FilePathMapping(local_path="service/1/patches/fix.patch", path="/patches/fix.patch")
        ]
        preset_dir = store.save(preset).parent
        (preset_dir / "service" / "1" / "patches").mkdir(parents=True)
        (preset_dir / "service" / "1" / "patches" / "fix.patch").write_text("--- a\n+++ b\n")
        destination = tmp_path / "deploy" / "qwen.dstack.yml"

        written = export_preset(
            store.get(preset.id),
            preset_dir=preset_dir,
            destination=destination,
            force=False,
        )

        assert written == [
            destination,
            tmp_path / "deploy" / "service" / "1" / "patches" / "fix.patch",
        ]
        data = yaml.safe_load(destination.read_text())
        assert data["type"] == "service"
        # An unnamed preset exports an unnamed service.
        assert data["name"] is None
        # Relative to the configuration file, which is how `dstack apply`
        # resolves `files` paths.
        assert data["files"] == [
            {"local_path": "service/1/patches/fix.patch", "path": "/patches/fix.patch"}
        ]
        assert (tmp_path / "deploy" / "service" / "1" / "patches" / "fix.patch").read_text() == (
            "--- a\n+++ b\n"
        )
        assert ServiceConfiguration.model_validate(data).model is not None

    def test_names_the_service_after_the_preset(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset().model_copy(update={"name": "qwen-fast"})
        preset_dir = store.save(preset).parent
        destination = tmp_path / "qwen.dstack.yml"

        export_preset(preset, preset_dir=preset_dir, destination=destination, force=False)

        data = yaml.safe_load(destination.read_text())
        assert data["name"] == "qwen-fast"

    def test_names_the_service_after_the_name_option(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset().model_copy(update={"name": "qwen-fast"})
        preset_dir = store.save(preset).parent
        destination = tmp_path / "qwen.dstack.yml"

        export_preset(
            preset,
            preset_dir=preset_dir,
            destination=destination,
            force=False,
            name="qwen-prod",
        )

        assert yaml.safe_load(destination.read_text())["name"] == "qwen-prod"

    def test_rejects_an_invalid_service_name(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        preset_dir = store.save(preset).parent
        destination = tmp_path / "qwen.dstack.yml"

        with pytest.raises(CLIError):
            export_preset(
                preset,
                preset_dir=preset_dir,
                destination=destination,
                force=False,
                name="Not_Valid!",
            )
        assert not destination.exists()

    def test_refuses_to_overwrite_without_force(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset_dir = store.save(get_preset()).parent
        destination = tmp_path / "qwen.dstack.yml"
        destination.write_text("existing")

        with pytest.raises(CLIError, match="already exists"):
            export_preset(
                store.get(get_preset().id),
                preset_dir=preset_dir,
                destination=destination,
                force=False,
            )
        assert destination.read_text() == "existing"

        export_preset(
            store.get(get_preset().id),
            preset_dir=preset_dir,
            destination=destination,
            force=True,
        )
        assert yaml.safe_load(destination.read_text())["type"] == "service"
