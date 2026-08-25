from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from dstack._internal.cli.models.presets import PulledPreset, VerifiedPreset
from dstack._internal.cli.services.presets import store as store_module
from dstack._internal.cli.services.presets.store import PresetStore
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.configurations import PresetConfiguration
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.files import FilePathMapping
from dstack._internal.core.models.presets import PortablePreset
from tests._internal.cli.common import get_preset

pytestmark = pytest.mark.windows


def _get_pulled_preset() -> PulledPreset:
    verified = get_preset()
    return PulledPreset(
        id="0b2b7b1e-9c1a-4a58-9d5a-3f6a1b2c3d4e",
        name="main/qwen",
        created_at=datetime(2026, 2, 3, 4, 5, tzinfo=timezone.utc),
        **{field: getattr(verified, field) for field in PortablePreset.model_fields},
    )


class TestPresetStore:
    def test_saves_and_lists_self_contained_preset(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()

        path = store.save(preset)

        assert path == (tmp_path / "presets" / "8f3a12c4" / "preset.yml")
        data = yaml.safe_load(path.read_text())
        assert data["base"] == preset.base
        assert data["id"] == preset.id
        assert data["repo"] == preset.repo
        assert data["created_at"] == "2026-01-02T03:04:00Z"
        assert data["status"] == "verified"
        assert "presets" not in data
        assert store.list() == [preset]
        assert store.get(preset.id) == preset
        assert not list(path.parent.glob("*.tmp"))

    def test_a_verified_document_loads_as_a_verified_preset(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        store.save(get_preset())

        loaded = store.get(get_preset().id)

        assert isinstance(loaded, VerifiedPreset)
        assert loaded.status == "verified"

    def test_loads_a_preset_written_by_0_21(self, tmp_path: Path):
        # A preset the released version wrote: the served repo under `model`,
        # the date under `submitted_at`, and a `status` that already tagged it.
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)
        path = tmp_path / "presets" / preset.id / "preset.yml"
        data = yaml.safe_load(path.read_text())
        data["model"] = data.pop("repo")
        data["submitted_at"] = data.pop("created_at")
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        loaded = store.get(preset.id)

        assert loaded == preset

    def test_loads_a_preset_that_requested_the_random_dataset(self, tmp_path: Path):
        # A synthetic preset the released version wrote with an explicit
        # `dataset: random` — the alias its own validator used to suggest. The
        # retired alias is rejected in a fresh configuration, but cannot
        # invalidate a record it was legal in: it reads back as what it meant,
        # a synthetic workload with no requested dataset.
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)
        path = tmp_path / "presets" / preset.id / "preset.yml"
        data = yaml.safe_load(path.read_text())
        data["configuration"]["dataset"] = "random"
        data["benchmark"]["workload"]["dataset"] = "random"
        data["benchmark"]["workload"]["shared_prefix_tokens"] = 0
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        loaded = store.get(preset.id)

        assert loaded is not None
        assert loaded.configuration.dataset is None
        assert loaded.benchmark.workload.dataset is None

    def test_loads_a_preset_that_predates_the_repo_field(self, tmp_path: Path):
        # Presets written before the rename store the served repo as `model`.
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)
        path = tmp_path / "presets" / preset.id / "preset.yml"
        data = yaml.safe_load(path.read_text())
        data["model"] = data.pop("repo")
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        loaded = store.get(preset.id)

        assert loaded is not None
        assert loaded.repo == preset.repo
        assert loaded == preset
        # The service's own client-facing model name is untouched by the upgrade.
        assert loaded.service.model == preset.service.model
        # Re-saving migrates the file to the current field name.
        store.save(loaded)
        assert "model" not in yaml.safe_load(path.read_text())

    def test_keeps_repo_when_the_file_already_uses_it(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)

        loaded = store.get(preset.id)

        assert loaded is not None
        assert loaded.repo == preset.repo

    def test_a_pulled_document_roundtrips_as_a_pulled_preset(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        pulled = _get_pulled_preset()

        store.save(pulled)
        loaded = store.get(pulled.id)

        # `status` tags the document as a pulled copy, so it loads as one.
        assert isinstance(loaded, PulledPreset)
        assert loaded == pulled
        assert store.list() == [pulled]
        data = yaml.safe_load((tmp_path / "presets" / pulled.id / "preset.yml").read_text())
        assert "configuration" not in data
        assert "best_trial" not in data
        assert data["status"] == "pulled"

    def test_loads_a_preset_that_predates_the_created_at_field(self, tmp_path: Path):
        # Presets written before the date was named for what it is store it as
        # `submitted_at`.
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)
        path = tmp_path / "presets" / preset.id / "preset.yml"
        data = yaml.safe_load(path.read_text())
        data["submitted_at"] = data.pop("created_at")
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        loaded = store.get(preset.id)

        assert loaded is not None
        assert loaded.created_at == preset.created_at
        assert loaded == preset

    def test_loads_a_pulled_copy_written_before_the_status_tag(self, tmp_path: Path):
        # Pulled copies predate the tag too, so the tag cannot simply default to
        # "verified": it is inferred from whether the creation context is there.
        store = PresetStore(tmp_path / "presets")
        pulled = _get_pulled_preset()
        store.save(pulled)
        path = tmp_path / "presets" / pulled.id / "preset.yml"
        data = yaml.safe_load(path.read_text())
        del data["status"]
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        loaded = store.get(pulled.id)

        assert isinstance(loaded, PulledPreset)
        assert loaded == pulled

    def test_loads_a_preset_written_before_the_status_tag(self, tmp_path: Path):
        # Only local creations could be stored before `status` tagged the union.
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)
        path = tmp_path / "presets" / preset.id / "preset.yml"
        data = yaml.safe_load(path.read_text())
        del data["status"]
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        loaded = store.get(preset.id)

        assert isinstance(loaded, VerifiedPreset)
        assert loaded == preset

    def test_reports_one_arms_errors_for_an_unreadable_preset(self, tmp_path: Path):
        # An untagged union reported both arms' errors, which buried the actual
        # problem in a wall of text about the shape the file never claimed to be.
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)
        path = tmp_path / "presets" / preset.id / "preset.yml"
        data = yaml.safe_load(path.read_text())
        del data["benchmark"]
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        with pytest.raises(CLIError) as excinfo:
            store.get(preset.id)

        message = str(excinfo.value)
        # Every reported error is located under the tag the file claims; the
        # untagged union used to add the other arm's errors on top.
        assert "1 validation error for" in message
        assert "verified.benchmark" in message
        assert "published." not in message

    def test_saving_same_id_overwrites_existing_preset(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)

        updated = preset.model_copy(update={"base": "Qwen/Another-Model", "context_length": 16384})
        store.save(updated)

        assert store.get(preset.id) == updated

    def test_ignores_directories_without_a_preset_file_but_keeps_them_deletable(
        self, tmp_path: Path
    ):
        root = tmp_path / "presets"
        store = PresetStore(root)
        # A creation session that never saved a preset.
        (root / "ab12cd34").mkdir(parents=True)
        (root / "ab12cd34" / "session.json").write_text("{}")

        assert store.list() == []
        assert store.delete("ab12cd34") is True
        assert not (root / "ab12cd34").exists()
        assert store.delete("ab12cd34") is False

    def test_refuses_an_id_that_could_name_a_directory_outside_the_store(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")

        # `D:x` is a drive-relative path on Windows, and `..` escapes anywhere.
        for preset_id in ["D:x", "..", "../presets", "a/b"]:
            with pytest.raises(CLIError, match="Invalid preset ID"):
                store.delete(preset_id)

    @pytest.mark.skipif(IS_WINDOWS, reason="symlink creation requires privileges on Windows")
    def test_refuses_to_delete_through_a_symlinked_directory(self, tmp_path: Path):
        root = tmp_path / "presets"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        (root / "ab12cd34").symlink_to(outside, target_is_directory=True)

        assert PresetStore(root).delete("ab12cd34") is False
        assert (outside / "keep.txt").read_text() == "keep"

    def test_skips_invalid_preset_on_list_but_keeps_it_deletable(self, tmp_path: Path, capsys):
        store = PresetStore(tmp_path / "presets")
        valid = get_preset().model_copy(update={"id": "01234567"})
        store.save(valid)
        path = store.save(get_preset())
        data = yaml.safe_load(path.read_text())
        data["benchmark"].pop("metrics")
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        # One corrupt file must not take down every read; the warning goes to
        # stderr so --json stdout stays parseable...
        assert [preset.id for preset in store.list()] == [valid.id]
        assert "benchmark" in capsys.readouterr().err
        # ...and the corrupt preset is still removable by ID.
        assert store.delete(get_preset().id) is True
        assert [preset.id for preset in store.list()] == [valid.id]

    def test_upgrades_pre_0_21_2_preset(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        directory = tmp_path / "presets" / "523096d6"
        directory.mkdir(parents=True)
        # The pre-0.21.2 shape: request echoed at the top level, the service
        # under `service`, and per-group verification under `validations`.
        (directory / "preset.yml").write_text(
            """
            base: deepseek-ai/DeepSeek-V4-Flash
            id: 523096d6
            name: dsv4-flash
            model: deepseek-ai/DeepSeek-V4-Flash-0731
            context_length: 1048576
            trial: 2
            min_context_length: 1048576
            max_ttft: 675
            created_at: '2026-08-13T15:11:13.334759+00:00'
            service:
              port: 80
              model: deepseek-ai/DeepSeek-V4-Flash
              commands: [vllm serve]
              image: vllm/vllm-openai-rocm
              priority: 0
              resources:
                cpu: 16..
                memory: 200GB..
                gpu: MI300X:192GB:1
                disk: 500GB..
            validations:
            - replicas:
              - resources:
                - cpu:
                    arch: x86
                    count: {min: 20, max: 20}
                  memory: {min: 240.0, max: 240.0}
                  gpu:
                    vendor: amd
                    name: [MI300X]
                    count: {min: 1, max: 1}
                    memory: {min: 192.0, max: 192.0}
                  disk:
                    size: {min: 720.0, max: 720.0}
              benchmark:
                tool: vllm bench serve
                tool_version: 0.26.1
                command: vllm bench serve --dataset-name random
                workload:
                  api: completions
                  num_requests: 16
                  input_tokens: 10000
                  output_tokens: 1500
                  concurrency: 4
                  shared_prefix_tokens: 0
                metrics:
                  successful_requests: 16
                  failed_requests: 0
                  duration_seconds: 137.42
                  total_input_tokens: 160000
                  total_output_tokens: 24000
                  output_tok_per_s: 174.65
                  per_user_tok_per_s: 43.66
                  ttft_ms: {mean: 1691.88, p50: 1240.31, p99: 4168.05}
                  tpot_ms: {mean: 21.57, p50: 21.84, p99: 23.28}
                target:
                  type: server-proxy
                client:
                  type: local
            """
        )

        preset = store.get("523096d6")

        assert preset is not None
        assert preset.name == "dsv4-flash"
        assert preset.best_trial == 2
        assert preset.configuration.model.base == "deepseek-ai/DeepSeek-V4-Flash"
        assert preset.configuration.min_context_length == 1048576
        assert preset.configuration.max_ttft == 675
        # The measured workload is the old format's only record of the
        # workload constraints; without it the objective would show defaults.
        assert preset.configuration.input_tokens == 10000
        assert preset.configuration.output_tokens == 1500
        assert preset.configuration.shared_prefix_tokens == 0
        assert preset.configuration.concurrency == 4
        # `priority` is not an excluded field, so the regrouping keeps it.
        assert preset.service.priority == 0
        assert [group.name for group in preset.verified_on] == [
            group.name for group in preset.service.replica_groups
        ]
        assert preset.verified_on[0].replicas[0].gpu.name == ["MI300X"]
        # The old format never recorded a dataset name for a synthetic workload.
        assert preset.benchmark.workload.dataset is None
        assert store.list() == [preset]

    def test_upgrade_maps_validation_replicas_to_replica_groups(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        directory = tmp_path / "presets" / "aa11bb22"
        directory.mkdir(parents=True)
        # One validation; its `replicas` entries follow the service's replica
        # group order, and each entry holds that group's per-replica resources.
        (directory / "preset.yml").write_text(
            """
            base: Qwen/Qwen3-32B
            id: aa11bb22
            name: null
            model: Qwen/Qwen3-32B
            context_length: 32768
            trial: 1
            created_at: '2026-08-13T15:11:13+00:00'
            service:
              port: 80
              model: Qwen/Qwen3-32B
              image: vllm/vllm-openai
              replicas:
              - name: small
                count: 1
                commands: [vllm serve]
                resources: {gpu: H100:80GB:1, disk: 100GB..}
              - name: large
                count: 2
                commands: [vllm serve]
                resources: {gpu: H200:141GB:1, disk: 100GB..}
            validations:
            - replicas:
              - resources:
                - cpu: {count: {min: 8, max: 8}}
                  memory: {min: 100.0, max: 100.0}
                  gpu: {name: [H100], count: {min: 1, max: 1}, memory: {min: 80.0, max: 80.0}}
                  disk: {size: {min: 100.0, max: 100.0}}
              - resources:
                - &r
                  cpu: {count: {min: 16, max: 16}}
                  memory: {min: 200.0, max: 200.0}
                  gpu: {name: [H200], count: {min: 1, max: 1}, memory: {min: 141.0, max: 141.0}}
                  disk: {size: {min: 200.0, max: 200.0}}
                - *r
              benchmark:
                tool: vllm bench serve
                tool_version: '1.0'
                command: vllm bench serve
                workload:
                  api: completions
                  num_requests: 8
                  input_tokens: 1024
                  output_tokens: 1024
                  concurrency: 2
                  shared_prefix_tokens: 0
                metrics:
                  successful_requests: 8
                  failed_requests: 0
                  duration_seconds: 10.0
                  total_input_tokens: 8192
                  total_output_tokens: 8192
                  output_tok_per_s: 819.2
                  per_user_tok_per_s: 100.0
                  ttft_ms: {mean: 100.0, p50: 100.0, p99: 200.0}
                  tpot_ms: {mean: 10.0, p50: 10.0, p99: 20.0}
            """
        )

        preset = store.get("aa11bb22")

        assert preset is not None
        assert [(group.name, len(group.replicas)) for group in preset.verified_on] == [
            ("small", 1),
            ("large", 2),
        ]
        assert preset.verified_on[0].replicas[0].gpu.name == ["H100"]
        assert preset.verified_on[1].replicas[0].gpu.name == ["H200"]

    def test_reports_pre_0_21_presets_as_one_summary_line(self, tmp_path: Path, capsys):
        store = PresetStore(tmp_path / "presets")
        bodies = {
            # The 0.20.x shape: no `trial` recorded, so it cannot be upgraded.
            "523096d6": "base: Qwen/Q\nid: 523096d6\nservice: {}\nvalidations: []\n",
            # A truncated file that lost its `service` block must degrade to
            # the same one-line message, not a traceback.
            "7cc991bd": "base: Qwen/Q\nid: 7cc991bd\ntrial: 1\nservice: null\nvalidations: null\n",
        }
        for preset_id, body in bodies.items():
            directory = tmp_path / "presets" / preset_id
            directory.mkdir(parents=True)
            (directory / "preset.yml").write_text(body)

        assert store.list() == []

        err = capsys.readouterr().err
        assert "2 presets created before dstack 0.21 cannot be read" in err
        assert "523096d6, 7cc991bd" in err
        assert err.count("before dstack 0.21") == 1
        assert "validation error" not in err

    def test_resolves_relative_file_paths_against_the_preset_directory(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        preset.service.files = [FilePathMapping(local_path="service/1/patches", path="/patches")]
        store.save(preset)

        loaded = store.get(preset.id)

        assert loaded.service.files[0].local_path == str(
            tmp_path / "presets" / preset.id / "service" / "1" / "patches"
        )

    def test_keeps_absolute_file_paths_as_saved(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        absolute = str(tmp_path / "elsewhere" / "patches")
        preset.service.files = [FilePathMapping(local_path=absolute, path="/patches")]
        store.save(preset)

        assert store.get(preset.id).service.files[0].local_path == absolute

    def test_release_name_keeps_file_paths_relative(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset().model_copy(update={"name": "qwen"})
        preset.service.files = [FilePathMapping(local_path="service/1/patches", path="/patches")]
        store.save(preset)

        # `release_name` re-saves a loaded preset, whose paths were resolved to
        # absolute; the saved file must come back out relative or the preset
        # directory silently stops being portable.
        store.release_name("qwen")

        data = yaml.safe_load((tmp_path / "presets" / preset.id / "preset.yml").read_text())
        assert data["service"]["files"][0]["local_path"] == "service/1/patches"

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

        store.save(preset)
        env = store.get(preset.id).service.env

        assert env["TOKENIZERS_PARALLELISM"] == "false"
        assert env["MODEL_LABEL"] == "monkey"
        assert env["HF_TOKEN"] == EnvSentinel(key="HF_TOKEN")


class TestParsePresetConfiguration:
    @pytest.mark.parametrize("key", ["base", "repo"])
    def test_accepts_nested_model_without_name(self, key: str):
        # The nested form is what stored presets use; user files may use it too.
        stream = StringIO(f"type: preset\nmodel:\n  {key}: Qwen/Qwen3.5-27B\n")

        configuration = store_module.parse_preset_configuration(stream)

        assert getattr(configuration.model, key) == "Qwen/Qwen3.5-27B"

    def test_accepts_nested_model_with_name(self):
        stream = StringIO(
            "type: preset\nmodel:\n  repo: community/Qwen3.5-27B-GPTQ-Int4\n  name: Qwen/Qwen3.5-27B\n"
        )

        configuration = store_module.parse_preset_configuration(stream)

        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"

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
            configuration = store_module.parse_preset_configuration(stream)

        warn.assert_not_called()
        assert configuration.model is not None


class TestResolvePresetPrompt:
    def test_resolves_inline_and_file_relative_to_configuration(self, tmp_path: Path):
        (tmp_path / "notes.md").write_text("From a file.\n")
        base = tmp_path
        inline = PresetConfiguration(name="q", base="Q/M", prompt="Inline text.")
        from_file = PresetConfiguration(name="q", base="Q/M", prompt={"path": "notes.md"})

        assert store_module.resolve_preset_prompt(inline, base) == "Inline text."
        assert store_module.resolve_preset_prompt(from_file, base) == "From a file."
        assert (
            store_module.resolve_preset_prompt(PresetConfiguration(name="q", base="Q/M"), base)
            is None
        )

    def test_rejects_missing_and_empty_prompt_files(self, tmp_path: Path):
        base = tmp_path
        (tmp_path / "empty.md").write_text("  \n")

        with pytest.raises(ConfigurationError, match="Failed to read"):
            store_module.resolve_preset_prompt(
                PresetConfiguration(name="q", base="Q/M", prompt={"path": "missing.md"}),
                base,
            )
        with pytest.raises(ConfigurationError, match="is empty"):
            store_module.resolve_preset_prompt(
                PresetConfiguration(name="q", base="Q/M", prompt={"path": "empty.md"}),
                base,
            )


class TestPresetNames:
    def test_finds_and_detaches_names(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        named = get_preset().model_copy(update={"name": "qwen"})
        store.save(named)
        store.save(get_preset().model_copy(update={"id": "01234567"}))

        assert store.find_by_name("qwen").id == named.id
        assert store.find_by_name("other") is None

        released = store.release_name("qwen")

        assert released.id == named.id
        assert store.find_by_name("qwen") is None
        assert store.get(named.id).name is None

    def test_find_by_id_or_name_resolves_a_pulled_qualified_name(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        # A pulled copy: UUID-named directory, qualified `<project>/<name>` name.
        pulled = get_preset(preset_id="0b2b7b1e-9c1a-4a58-9d5a-3f6a1b2c3d4e").model_copy(
            update={"name": "main/qwen"}
        )
        store.save(pulled)

        # A qualified name is never id-shaped, so the id lookup must not
        # reject it before the name lookup runs.
        assert store.find_by_id_or_name("main/qwen").id == pulled.id
        assert store.find_by_id_or_name(pulled.id) == store.get(pulled.id)

    def test_find_by_id_or_name_returns_none_for_an_unknown_qualified_ref(self, tmp_path: Path):
        store = PresetStore(tmp_path / "presets")
        store.save(get_preset())

        assert store.find_by_id_or_name("main/unknown") is None
