import json
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dstack._internal.cli.services.presets import output as presets_utils
from dstack._internal.cli.services.presets.store import PresetStore
from tests._internal.cli.common import plain_console, run_dstack_cli
from tests._internal.cli.preset_factories import get_preset

pytestmark = pytest.mark.windows


@contextmanager
def _patched_create_preset(**create_kwargs):
    """Patch the create pipeline; yields the create_preset mock."""
    with (
        patch("dstack.api.Client.from_config"),
        patch(
            "dstack._internal.cli.commands.preset.plan_preset",
            return_value=("fleet-a",),
        ),
        patch("dstack._internal.cli.commands.preset.create_preset", **create_kwargs) as create,
    ):
        yield create


@pytest.fixture(autouse=True)
def mock_ssh_client_info():
    # Keeps every CLI invocation in this module off the real ssh binary.
    with patch("dstack._internal.cli.main.get_ssh_client_info"):
        yield


class TestPresetLocalCommands:
    def test_handles_keyboard_interrupt(self, tmp_path, capsys):
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nname: qwen\nmodel:\n  base: Qwen/Qwen3.5-27B\nmax_trials: 1\n"
        )

        with _patched_create_preset(side_effect=KeyboardInterrupt):
            exit_code = run_dstack_cli(
                ["preset", "create", "-y", "-f", str(configuration_path)],
                home_dir=tmp_path,
            )

        assert exit_code == 0
        # create reports its own Ctrl+C outcome (Detached / interrupted) via the
        # interrupt handler, so the command layer stays silent — no generic line.
        assert "Operation interrupted by user" not in capsys.readouterr().out

    def test_create_ends_quietly_when_stopped_from_another_cli(self, tmp_path, capsys):
        from dstack._internal.cli.services.presets.create import CreationStopped

        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nname: qwen\nmodel:\n  base: Qwen/Qwen3.5-27B\nmax_trials: 1\n"
        )

        with _patched_create_preset(side_effect=CreationStopped):
            exit_code = run_dstack_cli(
                ["preset", "create", "-y", "-f", str(configuration_path)],
                home_dir=tmp_path,
            )

        # The stopping CLI reported the interruption; the owner just ends.
        assert exit_code == 0
        assert "Traceback" not in capsys.readouterr().err

    def test_create_requires_max_trials(self, tmp_path, capsys):
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text("type: preset\nname: qwen\nbase: Qwen/Qwen3.5-27B\n")

        with _patched_create_preset() as create:
            exit_code = run_dstack_cli(
                ["preset", "create", "-y", "-f", str(configuration_path)],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "max_trials is required" in captured.out + captured.err
        create.assert_not_called()

    def _list_output(self, tmp_path, args, *, created_at):
        output = StringIO()
        with (
            patch("dstack.api.Client.from_config") as from_config,
            patch.object(presets_utils, "console", plain_console(output)),
            patch.object(presets_utils, "pretty_date", return_value="2 months ago") as pretty_date,
        ):
            assert run_dstack_cli(args, home_dir=tmp_path) == 0
            from_config.assert_not_called()
            pretty_date.assert_called_once_with(created_at)
        return output.getvalue()

    def test_lists_presets_without_api_client(self, tmp_path):
        preset = get_preset()
        PresetStore(tmp_path / ".dstack" / "presets").save(preset)

        output = self._list_output(tmp_path, ["preset", "list"], created_at=preset.created_at)

        assert "Qwen/Qwen3.5-27B" in output
        assert "8f3a12c4" in output
        # The repo row is shown only in verbose mode.
        assert "repo=community/Qwen3.5-27B-GPTQ-Int4" not in output
        # The context column is shown only in verbose mode.
        assert "CONTEXT" not in output
        assert "BENCHMARK" in output
        assert "32K" not in output
        assert "42.1" in output
        assert "con=1" in "".join(output.split())
        assert "tok/s" in output
        assert "TTFT" in output
        assert "108ms" in output
        assert "A6000:48GB:1" not in output

    def test_verbose_list_adds_repo_and_context(self, tmp_path):
        preset = get_preset()
        PresetStore(tmp_path / ".dstack" / "presets").save(preset)

        joined_verbose = "".join(
            self._list_output(
                tmp_path, ["preset", "list", "-v"], created_at=preset.created_at
            ).split()
        )

        # Verbose adds only the repo and the ctx= benchmark prefix.
        assert "repo=community/Qwen3.5-27B-GPTQ-Int4" in joined_verbose
        assert "ctx=32K" in joined_verbose
        assert "con=1" in joined_verbose
        assert "hardware=" not in joined_verbose

    def test_deletes_preset_without_api_client(self, tmp_path):
        preset = get_preset()
        PresetStore(tmp_path / ".dstack" / "presets").save(preset)

        with patch("dstack.api.Client.from_config") as from_config:
            assert run_dstack_cli(["preset", "delete", preset.id, "-y"], home_dir=tmp_path) == 0
            from_config.assert_not_called()

        assert PresetStore(tmp_path / ".dstack" / "presets").list() == []

    def test_gets_complete_preset_as_json_without_api_client(self, tmp_path, capsys):
        preset = get_preset()
        PresetStore(tmp_path / ".dstack" / "presets").save(preset)

        with patch("dstack.api.Client.from_config") as from_config:
            assert (
                run_dstack_cli(
                    ["preset", "get", preset.id, "--json"],
                    home_dir=tmp_path,
                )
                == 0
            )
            from_config.assert_not_called()

        data = json.loads(capsys.readouterr().out)
        assert data["id"] == preset.id
        assert data["created_at"] == preset.created_at.isoformat()
        assert data["context_length"] == 32768
        assert data["validations"][0]["benchmark"]["metrics"]["total_output_tokens"] == 2048

    @pytest.mark.parametrize(
        "args",
        [
            ["preset", "--json"],
            ["preset", "list", "--json"],
        ],
    )
    def test_lists_complete_presets_as_json(self, tmp_path, capsys, args):
        preset = get_preset()
        PresetStore(tmp_path / ".dstack" / "presets").save(preset)

        assert run_dstack_cli(args, home_dir=tmp_path) == 0

        output = json.loads(capsys.readouterr().out)
        assert len(output["presets"]) == 1
        data = output["presets"][0]
        assert data["id"] == preset.id
        assert data["created_at"] == preset.created_at.isoformat()
        assert data["context_length"] == 32768
        assert data["validations"][0]["benchmark"]["metrics"]["total_output_tokens"] == 2048

    @pytest.mark.parametrize("flag_attribute", [("--base", "base"), ("--repo", "model")])
    def test_deletes_all_presets_of_model_keeping_others_without_api_client(
        self, tmp_path, flag_attribute
    ):
        flag, attribute = flag_attribute
        preset = get_preset()
        store = PresetStore(tmp_path / ".dstack" / "presets")
        store.save(preset)
        store.save(preset.copy(update={"id": "01234567"}))
        # A preset of a different model must survive the delete.
        store.save(
            preset.copy(update={"id": "89abcdef", "base": "meta/Llama-4", "model": "meta/Llama-4"})
        )

        with patch("dstack.api.Client.from_config") as from_config:
            assert (
                run_dstack_cli(
                    ["preset", "delete", flag, getattr(preset, attribute), "-y"],
                    home_dir=tmp_path,
                )
                == 0
            )
            from_config.assert_not_called()

        assert [remaining.id for remaining in store.list()] == ["89abcdef"]

    @pytest.mark.parametrize("flag_attribute", [("--base", "base"), ("--repo", "model")])
    def test_lists_presets_filtered_by_model(self, tmp_path, capsys, flag_attribute):
        flag, attribute = flag_attribute
        preset = get_preset()
        store = PresetStore(tmp_path / ".dstack" / "presets")
        store.save(preset)
        store.save(
            preset.copy(update={"id": "01234567", "base": "meta/Llama-4", "model": "meta/Llama-4"})
        )

        args = ["preset", "list", "--json", flag, getattr(preset, attribute)]
        assert run_dstack_cli(args, home_dir=tmp_path) == 0

        output = json.loads(capsys.readouterr().out)
        assert [entry["id"] for entry in output["presets"]] == [preset.id]

    def test_corrupt_preset_stays_deletable_and_keeps_json_parseable(self, tmp_path, capsys):
        preset = get_preset()
        store = PresetStore(tmp_path / ".dstack" / "presets")
        store.save(preset)
        corrupt_dir = tmp_path / ".dstack" / "presets" / "deadbeef"
        corrupt_dir.mkdir(parents=True)
        (corrupt_dir / "preset.yaml").write_text("{not valid yaml")

        # The corrupt-file warning goes to stderr, so --json stdout stays parseable.
        assert run_dstack_cli(["preset", "list", "--json"], home_dir=tmp_path) == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert [entry["id"] for entry in output["presets"]] == [preset.id]
        assert "Invalid preset file" in captured.err

        # And the corrupt preset is still removable through the CLI.
        assert run_dstack_cli(["preset", "delete", "deadbeef", "-y"], home_dir=tmp_path) == 0
        assert not corrupt_dir.exists()
        assert [remaining.id for remaining in store.list()] == [preset.id]

    def test_merges_profile_configuration_and_cli_args(self, tmp_path):
        (tmp_path / ".dstack").mkdir()
        (tmp_path / ".dstack" / "profiles.yml").write_text(
            """profiles:
  - name: gpu
    default: true
    backends: [aws]
    regions: [profile-region]
    max_price: 0.25
    spot_policy: spot
"""
        )
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            """type: preset
name: file-name
model:
  base: Qwen/Qwen3.5-27B
regions: [file-region]
max_price: 0.5
max_trials: 1
env:
  - HF_TOKEN
"""
        )
        preset = get_preset()
        result = SimpleNamespace(
            preset=preset,
            path=tmp_path / "preset.yaml",
            final_run_name="qwen-build-2",
        )

        with _patched_create_preset(return_value=result) as create:
            exit_code = run_dstack_cli(
                [
                    "preset",
                    "create",
                    "-y",
                    "-f",
                    str(configuration_path),
                    "--name",
                    "cli-name",
                    "--backend",
                    "gcp",
                    "--max-price",
                    "0.75",
                    "--fleet",
                    "cli-fleet",
                    "--debug",
                ],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 0
        configuration = create.call_args.kwargs["configuration"]
        assert configuration.name == "cli-name"
        assert configuration.backends == ["gcp"]
        assert configuration.regions == ["file-region"]
        assert configuration.max_price == 0.75
        assert configuration.spot_policy.value == "spot"
        assert [fleet.format() for fleet in configuration.fleets] == ["cli-fleet"]
        assert create.call_args.kwargs["debug"] is True

    def test_apply_passes_selected_profile_and_preset_id(self, tmp_path):
        extra_args = ["--id", "cli-preset"]
        (tmp_path / ".dstack").mkdir()
        (tmp_path / ".dstack" / "profiles.yml").write_text(
            "profiles:\n  - name: gpu\n    max_price: 0.5\n"
        )
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nname: qwen\nmodel:\n  base: Qwen/Qwen3.5-27B\n"
        )

        with (
            patch("dstack.api.Client.from_config"),
            patch("dstack._internal.cli.commands.preset.apply_preset") as apply,
        ):
            args = [
                "preset",
                "apply",
                "-f",
                str(configuration_path),
                "--profile",
                "gpu",
                *extra_args,
            ]
            exit_code = run_dstack_cli(
                args,
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 0
        assert apply.call_args.kwargs["profile_name"] == "gpu"
        assert apply.call_args.kwargs["preset_id"] == "cli-preset"
        assert apply.call_args.kwargs["configuration"].max_price == 0.5

    def test_apply_requires_preset_id(self, tmp_path, capsys):
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nname: qwen\nmodel:\n  base: Qwen/Qwen3.5-27B\n"
        )

        with patch("dstack._internal.cli.commands.preset.apply_preset") as apply:
            exit_code = run_dstack_cli(
                ["preset", "apply", "-f", str(configuration_path)],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 2
        assert "--id" in capsys.readouterr().err
        apply.assert_not_called()


class TestPresetNameClaims:
    def test_create_detaches_the_name_from_the_old_preset(self, tmp_path):
        preset = get_preset().copy(update={"name": "qwen"})
        store = PresetStore(tmp_path / ".dstack" / "presets")
        store.save(preset)
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nname: qwen\nbase: Qwen/Qwen3.5-27B\nmax_trials: 1\n"
        )
        result = SimpleNamespace(
            preset=preset, path=tmp_path / "preset.yaml", final_run_name="qwen-1"
        )

        with _patched_create_preset(return_value=result) as create:
            exit_code = run_dstack_cli(
                ["preset", "create", "-f", str(configuration_path), "-y"],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 0
        create.assert_called_once()
        assert store.get(preset.id).name is None

    def test_create_without_confirmation_exits_before_creating(self, tmp_path):
        preset = get_preset().copy(update={"name": "qwen"})
        store = PresetStore(tmp_path / ".dstack" / "presets")
        store.save(preset)
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nname: qwen\nbase: Qwen/Qwen3.5-27B\nmax_trials: 1\n"
        )

        with (
            _patched_create_preset() as create,
            patch("dstack._internal.cli.commands.preset.confirm_ask", return_value=False),
        ):
            exit_code = run_dstack_cli(
                ["preset", "create", "-f", str(configuration_path)],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 0
        create.assert_not_called()
        assert store.get(preset.id).name == "qwen"

    def test_get_and_delete_resolve_names(self, tmp_path, capsys):
        preset = get_preset().copy(update={"name": "qwen"})
        PresetStore(tmp_path / ".dstack" / "presets").save(preset)

        assert run_dstack_cli(["preset", "get", "qwen", "--json"], home_dir=tmp_path) == 0
        assert json.loads(capsys.readouterr().out)["id"] == preset.id

        assert run_dstack_cli(["preset", "delete", "qwen", "-y"], home_dir=tmp_path) == 0
        assert PresetStore(tmp_path / ".dstack" / "presets").list() == []

    def test_create_always_asks_even_without_a_name_conflict(self, tmp_path):
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text("type: preset\nbase: Qwen/Qwen3.5-27B\nmax_trials: 1\n")

        with (
            _patched_create_preset() as create,
            patch(
                "dstack._internal.cli.commands.preset.confirm_ask", return_value=False
            ) as confirm,
        ):
            exit_code = run_dstack_cli(
                ["preset", "create", "-f", str(configuration_path)],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 0
        confirm.assert_called_once_with("Create the preset?")
        create.assert_not_called()
