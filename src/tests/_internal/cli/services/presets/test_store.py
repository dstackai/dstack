from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from pydantic import ValidationError

from dstack._internal.cli.models.configurations import PresetConfiguration
from dstack._internal.cli.models.preset_agent import AGENT_FINAL_REPORT_JSON_SCHEMA
from dstack._internal.cli.models.presets import (
    PresetBenchmark,
    PresetBenchmarkLatency,
    PresetBenchmarkMetrics,
    PresetBenchmarkWorkload,
)
from dstack._internal.cli.services.presets import store as store_module
from dstack._internal.cli.services.presets.store import PresetStore
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.envs import EnvSentinel
from tests._internal.cli.preset_factories import (
    get_preset,
    get_preset_benchmark,
)

pytestmark = pytest.mark.windows


class TestPresetBenchmark:
    def test_agent_schema_matches_benchmark_model(self):
        schema = AGENT_FINAL_REPORT_JSON_SCHEMA["properties"]["benchmark"]
        assert set(schema["properties"]) == set(PresetBenchmark.__fields__) - {
            "target",
            "client",
        }
        assert set(schema["required"]) == set(schema["properties"])
        workload_schema = schema["properties"]["workload"]
        metrics_schema = schema["properties"]["metrics"]
        assert set(workload_schema["properties"]) == set(PresetBenchmarkWorkload.__fields__)
        assert set(workload_schema["required"]) == set(workload_schema["properties"])
        assert set(metrics_schema["properties"]) == set(PresetBenchmarkMetrics.__fields__)
        assert set(metrics_schema["required"]) == set(metrics_schema["properties"])
        assert set(metrics_schema["properties"]["ttft_ms"]["properties"]) == set(
            PresetBenchmarkLatency.__fields__
        )

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("failed_requests", 1, "must not include failed requests"),
            ("successful_requests", 15, "must match workload.num_requests"),
        ],
    )
    def test_rejects_inconsistent_successful_metrics(self, field, value, error):
        data = get_preset_benchmark().dict()
        data["metrics"][field] = value
        with pytest.raises(ValidationError, match=error):
            PresetBenchmark.parse_obj(data)

    def test_rejects_tool_specific_metrics(self):
        data = get_preset_benchmark().dict()
        data["metrics"]["tool_specific"] = 1

        with pytest.raises(ValidationError, match="extra fields not permitted"):
            PresetBenchmark.parse_obj(data)


class TestPresetStore:
    def test_saves_and_lists_self_contained_preset(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()

        path = store.save(preset)

        assert path == (tmp_path / "presets" / "8f3a12c4" / "preset.yaml")
        data = yaml.safe_load(path.read_text())
        assert data["base"] == preset.base
        assert data["id"] == preset.id
        assert data["model"] == preset.model
        assert data["created_at"] == preset.created_at.isoformat()
        assert "presets" not in data
        assert store.list() == [preset]
        assert store.get(preset.id) == preset
        assert not list(path.parent.glob("*.tmp"))

    def test_replaces_same_preset_id_atomically(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)

        updated = preset.copy(update={"context_length": 16384})
        store.save(updated)

        assert store.get(updated.id) == updated

    def test_same_id_save_overwrites(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)
        store.save(preset.copy(update={"base": "Qwen/Another-Model"}))

        loaded = store.get(preset.id)
        assert loaded is not None
        assert loaded.base == "Qwen/Another-Model"

    def test_migrates_legacy_layout_and_archives_on_delete(self, tmp_path: Path):
        root = tmp_path / "presets"
        store = PresetStore(root)
        preset = get_preset()
        legacy = root / "models--Qwen--Qwen3.5-27B"
        legacy.mkdir(parents=True)
        (legacy / f"{preset.id}.yaml").write_text(
            yaml.safe_dump(
                yaml.safe_load(PresetStore(tmp_path / "tmp").save(preset).read_text()),
                sort_keys=False,
            )
        )

        assert store.list() == [preset]
        assert (root / preset.id / "preset.yaml").is_file()
        assert not legacy.exists()

        assert store.delete(preset.id) is True
        assert store.get(preset.id) is None
        assert (root / ".archive" / preset.id / "preset.yaml").is_file()
        assert store.list() == []

    def test_rejects_preset_without_successful_benchmark(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        path = store.save(get_preset())
        data = yaml.safe_load(path.read_text())
        data["validations"][0].pop("benchmark")
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        with pytest.raises(CLIError, match="benchmark"):
            store.list()

    def test_preserves_literal_env_values(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        preset.service.env.update(
            {
                "TOKENIZERS_PARALLELISM": "false",
                "MODEL_LABEL": "monkey",
                "HF_TOKEN": EnvSentinel(key="HF_TOKEN"),
            }
        )

        path = store.save(preset)
        env = yaml.safe_load(path.read_text())["service"]["env"]

        assert "TOKENIZERS_PARALLELISM=false" in env
        assert "MODEL_LABEL=monkey" in env
        assert "HF_TOKEN" in env


class TestParsePresetConfiguration:
    @pytest.mark.parametrize("key", ["base", "repo"])
    def test_warns_on_nested_model_without_name(self, key: str):
        stream = StringIO(f"type: preset\nmodel:\n  {key}: Qwen/Qwen3.5-27B\n")

        with patch.object(store_module, "warn") as warn:
            configuration = store_module._parse_preset_configuration(stream)

        warn.assert_called_once()
        assert f"model.{key}" in warn.call_args.args[0]
        assert f"`{key}:`" in warn.call_args.args[0]
        assert configuration.model is not None

    @pytest.mark.parametrize(
        "body",
        [
            "base: Qwen/Qwen3.5-27B\n",
            "repo: Qwen/Qwen3.5-27B\n",
            "model: Qwen/Qwen3.5-27B\n",
            "model:\n  repo: community/Qwen3.5-27B-GPTQ-Int4\n  name: Qwen/Qwen3.5-27B\n",
        ],
    )
    def test_does_not_warn_on_preferred_syntax(self, body: str):
        stream = StringIO(f"type: preset\n{body}")

        with patch.object(store_module, "warn") as warn:
            configuration = store_module._parse_preset_configuration(stream)

        warn.assert_not_called()
        assert configuration.model is not None


class TestResolvePresetPrompt:
    def test_resolves_inline_and_file_relative_to_configuration(self, tmp_path: Path):
        (tmp_path / "notes.md").write_text("From a file.\n")
        configuration_path = str(tmp_path / "preset.dstack.yml")
        inline = PresetConfiguration(name="q", base="Q/M", prompt="Inline text.")
        from_file = PresetConfiguration(name="q", base="Q/M", prompt={"path": "notes.md"})

        assert store_module.resolve_preset_prompt(inline, configuration_path) == "Inline text."
        assert store_module.resolve_preset_prompt(from_file, configuration_path) == "From a file."
        assert (
            store_module.resolve_preset_prompt(
                PresetConfiguration(name="q", base="Q/M"), configuration_path
            )
            is None
        )

    def test_rejects_missing_and_empty_prompt_files(self, tmp_path: Path):
        configuration_path = str(tmp_path / "preset.dstack.yml")
        (tmp_path / "empty.md").write_text("  \n")

        with pytest.raises(ConfigurationError, match="Failed to read"):
            store_module.resolve_preset_prompt(
                PresetConfiguration(name="q", base="Q/M", prompt={"path": "missing.md"}),
                configuration_path,
            )
        with pytest.raises(ConfigurationError, match="is empty"):
            store_module.resolve_preset_prompt(
                PresetConfiguration(name="q", base="Q/M", prompt={"path": "empty.md"}),
                configuration_path,
            )


class TestPresetNames:
    def test_finds_and_detaches_names(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        named = get_preset().copy(update={"name": "qwen"})
        store.save(named)
        store.save(get_preset().copy(update={"id": "01234567"}))

        assert store.find_by_name("qwen").id == named.id
        assert store.find_by_name("other") is None

        released = store.release_name("qwen")

        assert released.id == named.id
        assert store.find_by_name("qwen") is None
        assert store.get(named.id).name is None
