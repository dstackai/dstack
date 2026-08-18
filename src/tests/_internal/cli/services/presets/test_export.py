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

        # The store-internal `service/<k>/` record prefix stays out of the
        # exported layout.
        assert written == [
            destination,
            tmp_path / "deploy" / "patches" / "fix.patch",
        ]
        data = yaml.safe_load(destination.read_text())
        assert data["type"] == "service"
        # Relative to the configuration file, which is how `dstack apply`
        # resolves `files` paths.
        assert data["files"] == [{"local_path": "patches/fix.patch", "path": "/patches/fix.patch"}]
        assert (tmp_path / "deploy" / "patches" / "fix.patch").read_text() == "--- a\n+++ b\n"
        assert ServiceConfiguration.model_validate(data).model is not None

    def test_exports_a_trial_record_file_without_its_record_prefix(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        preset.service.files = [
            FilePathMapping(local_path="trials/3/patches/fix.patch", path="/patches/fix.patch")
        ]
        preset_dir = store.save(preset).parent
        (preset_dir / "trials" / "3" / "patches").mkdir(parents=True)
        (preset_dir / "trials" / "3" / "patches" / "fix.patch").write_text("--- a\n+++ b\n")
        destination = tmp_path / "deploy" / "qwen.dstack.yml"

        written = export_preset(
            store.get(preset.id),
            preset_dir=preset_dir,
            destination=destination,
            force=False,
        )

        assert written == [destination, tmp_path / "deploy" / "patches" / "fix.patch"]
        data = yaml.safe_load(destination.read_text())
        assert data["files"] == [{"local_path": "patches/fix.patch", "path": "/patches/fix.patch"}]

    def test_keeps_record_paths_when_flattening_would_collide(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        preset.service.files = [
            FilePathMapping(local_path="service/1/patches/fix.patch", path="/patches/a.patch"),
            FilePathMapping(local_path="service/2/patches/fix.patch", path="/patches/b.patch"),
        ]
        preset_dir = store.save(preset).parent
        for attempt, content in (("1", "one\n"), ("2", "two\n")):
            (preset_dir / "service" / attempt / "patches").mkdir(parents=True)
            (preset_dir / "service" / attempt / "patches" / "fix.patch").write_text(content)
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
            tmp_path / "deploy" / "service" / "2" / "patches" / "fix.patch",
        ]
        data = yaml.safe_load(destination.read_text())
        assert data["files"] == [
            {"local_path": "service/1/patches/fix.patch", "path": "/patches/a.patch"},
            {"local_path": "service/2/patches/fix.patch", "path": "/patches/b.patch"},
        ]
        assert (tmp_path / "deploy" / "service" / "1" / "patches" / "fix.patch").read_text() == (
            "one\n"
        )
        assert (tmp_path / "deploy" / "service" / "2" / "patches" / "fix.patch").read_text() == (
            "two\n"
        )

    def test_treats_paths_differing_only_in_case_as_a_collision(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        preset.service.files = [
            FilePathMapping(local_path="service/1/patches/Fix.patch", path="/patches/a.patch"),
            FilePathMapping(local_path="service/2/patches/fix.patch", path="/patches/b.patch"),
        ]
        preset_dir = store.save(preset).parent
        for attempt, name in (("1", "Fix.patch"), ("2", "fix.patch")):
            (preset_dir / "service" / attempt / "patches").mkdir(parents=True)
            (preset_dir / "service" / attempt / "patches" / name).write_text(name)
        destination = tmp_path / "deploy" / "qwen.dstack.yml"

        export_preset(
            store.get(preset.id),
            preset_dir=preset_dir,
            destination=destination,
            force=False,
        )

        data = yaml.safe_load(destination.read_text())
        assert data["files"] == [
            {"local_path": "service/1/patches/Fix.patch", "path": "/patches/a.patch"},
            {"local_path": "service/2/patches/fix.patch", "path": "/patches/b.patch"},
        ]

    def test_keeps_record_paths_when_a_file_would_land_on_the_configuration(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        preset.service.files = [
            FilePathMapping(local_path="service/1/qwen.dstack.yml", path="/extra/qwen.dstack.yml")
        ]
        preset_dir = store.save(preset).parent
        (preset_dir / "service" / "1").mkdir(parents=True)
        (preset_dir / "service" / "1" / "qwen.dstack.yml").write_text("extra\n")
        destination = tmp_path / "deploy" / "qwen.dstack.yml"

        written = export_preset(
            store.get(preset.id),
            preset_dir=preset_dir,
            destination=destination,
            force=False,
        )

        assert written == [destination, tmp_path / "deploy" / "service" / "1" / "qwen.dstack.yml"]
        data = yaml.safe_load(destination.read_text())
        assert data["type"] == "service"
        assert data["files"] == [
            {"local_path": "service/1/qwen.dstack.yml", "path": "/extra/qwen.dstack.yml"}
        ]
        assert (tmp_path / "deploy" / "service" / "1" / "qwen.dstack.yml").read_text() == "extra\n"

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
