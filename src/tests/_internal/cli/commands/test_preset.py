import argparse
import json
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dstack._internal.cli.commands.preset import _check_stdin_configuration_confirmable
from dstack._internal.cli.models.preset_agent import PresetSessionWorkspace
from dstack._internal.cli.services.presets import output as presets_utils
from dstack._internal.cli.services.presets.store import PresetStore
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError
from dstack._internal.utils.common import render_datetime_as_api
from tests._internal.cli.common import (
    get_preset,
    get_session_run,
    get_session_state,
    plain_console,
    run_dstack_cli,
)

pytestmark = pytest.mark.windows


@contextmanager
def _patched_create_preset(**create_kwargs):
    """Patch the create pipeline; yields the create_preset mock."""
    with (
        patch("dstack.api.Client.from_config"),
        patch(
            "dstack._internal.cli.services.configurators.preset.plan_preset",
            return_value=("fleet-a",),
        ),
        patch(
            "dstack._internal.cli.services.configurators.preset.create_preset", **create_kwargs
        ) as create,
    ):
        yield create


@pytest.fixture(autouse=True)
def mock_ssh_client_info():
    # Keeps every CLI invocation in this module off the real ssh binary.
    with patch("dstack._internal.cli.main.get_ssh_client_info"):
        yield


class TestStdinConfiguration:
    def test_create_from_stdin_requires_yes(self):
        # Same rule as `dstack apply`: the prompt cannot read from a stdin that
        # is the configuration itself.
        args = argparse.Namespace(yes=False, configuration_file="-")
        with pytest.raises(CLIError, match="stdin"):
            _check_stdin_configuration_confirmable(args)

        _check_stdin_configuration_confirmable(
            argparse.Namespace(yes=True, configuration_file="-")
        )


class TestPresetLocalCommands:
    def test_handles_keyboard_interrupt(self, tmp_path, capsys):
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nname: qwen\nbase: Qwen/Qwen3.5-27B\ntrials: 1\nconcurrency: 8\nmax_ttft: 5000\nmin_context_length: 8192\n"
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

    def test_resume_uses_the_configuration_and_prompt_pinned_at_creation(self, tmp_path):
        session_dir = tmp_path / ".dstack" / "presets" / "ab12cd34"
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text(
            json.dumps(
                get_session_state(
                    status="interrupted", run=get_session_run(claude_session_id="sid-1")
                ).model_dump(mode="json")
            )
        )
        (session_dir / "preset.dstack.yml").write_text(
            "type: preset\nbase: Qwen/Qwen3.5-27B\nmin_context_length: 8192\n"
        )
        (session_dir / "prompt.md").write_text("go deep\n")

        with (
            patch("dstack.api.Client.from_config"),
            patch("dstack._internal.cli.commands.preset.create_preset") as create,
        ):
            exit_code = run_dstack_cli(
                ["preset", "resume", "ab12cd34"], home_dir=tmp_path, repo_dir=tmp_path
            )

        assert exit_code == 0
        kwargs = create.call_args.kwargs
        assert kwargs["resume_session"].preset_id == "ab12cd34"
        assert kwargs["configuration"].model.base == "Qwen/Qwen3.5-27B"
        assert kwargs["user_prompt"] == "go deep"

    def test_get_returns_the_requested_configuration_for_an_unfinished_preset(
        self, tmp_path, capsys
    ):
        session_dir = tmp_path / ".dstack" / "presets" / "ab12cd34"
        session_dir.mkdir(parents=True)
        session_dir.joinpath("session.json").write_text(
            json.dumps(
                get_session_state(status="running", name="in-flight").model_dump(mode="json")
            )
        )
        session_dir.joinpath("preset.dstack.yml").write_text(
            "type: preset\nbase: Qwen/Qwen3.5-27B\nmin_context_length: 8192\n"
        )

        exit_code = run_dstack_cli(
            ["preset", "get", "--json", "in-flight"], home_dir=tmp_path, repo_dir=tmp_path
        )

        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "running"
        assert data["id"] == "ab12cd34"
        assert data["configuration"]["model"]["base"] == "Qwen/Qwen3.5-27B"
        assert "service" not in data

    def test_create_ends_quietly_when_stopped_from_another_cli(self, tmp_path, capsys):
        from dstack._internal.cli.services.presets.create import CreationStopped

        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nname: qwen\nbase: Qwen/Qwen3.5-27B\ntrials: 1\nconcurrency: 8\nmax_ttft: 5000\nmin_context_length: 8192\n"
        )

        with _patched_create_preset(side_effect=CreationStopped):
            exit_code = run_dstack_cli(
                ["preset", "create", "-y", "-f", str(configuration_path)],
                home_dir=tmp_path,
            )

        # The stopping CLI reported the interruption; the owner just ends.
        assert exit_code == 0
        assert "Traceback" not in capsys.readouterr().err

    def test_create_requires_trials(self, tmp_path, capsys):
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
        assert "trials is required" in captured.out + captured.err
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

        output = self._list_output(tmp_path, ["preset", "list"], created_at=preset.submitted_at)

        assert "Qwen/Qwen3.5-27B" in output
        assert "8f3a12c4" in output
        # The repo row is shown only in verbose mode.
        assert "repo=community/Qwen3.5-27B-GPTQ-Int4" not in output
        # The benchmark always carries the context and workload that define its
        # number. The context that was *required* waits for `-v`, and comes from
        # the creation record, which a preset saved on its own does not have.
        assert "CONTEXT" not in output
        assert "CONSTRAINTS" in output
        assert "BENCHMARK" in output
        assert "ctx=32K" in "".join(output.split())
        assert "ctx>=" not in "".join(output.split())
        assert "io=1K/128" in "".join(output.split())
        # 42.1 is the aggregate, verbose-only; the default row shows per-user 1/TPOT.
        assert "133" in output
        assert "c=1" in "".join(output.split())
        assert "tps/user=" in "".join(output.split())
        assert "ttft=" in "".join(output.split())
        assert "ttft=[/]108" in "".join(output.split()) or "ttft=108" in "".join(output.split())
        assert "A6000:48GB:1" not in output

    def test_verbose_list_adds_repo(self, tmp_path):
        preset = get_preset()
        PresetStore(tmp_path / ".dstack" / "presets").save(preset)

        joined_verbose = "".join(
            self._list_output(
                tmp_path, ["preset", "list", "-v"], created_at=preset.submitted_at
            ).split()
        )

        # Verbose adds only the repo row.
        assert "repo=community/Qwen3.5-27B-GPTQ-Int4" in joined_verbose
        assert "ctx=32K" in joined_verbose
        assert "c=1" in joined_verbose
        assert "hardware=" not in joined_verbose

    def test_deletes_preset_without_api_client(self, tmp_path):
        preset = get_preset()
        PresetStore(tmp_path / ".dstack" / "presets").save(preset)

        with patch("dstack.api.Client.from_config") as from_config:
            assert run_dstack_cli(["preset", "delete", preset.id, "-y"], home_dir=tmp_path) == 0
            from_config.assert_not_called()

        assert PresetStore(tmp_path / ".dstack" / "presets").list() == []

    def test_deletes_an_interrupted_creation_that_never_saved_a_preset(self, tmp_path, capsys):
        session_dir = self._session(tmp_path, status="interrupted")

        assert run_dstack_cli(["preset", "delete", "smoke", "-y"], home_dir=tmp_path) == 0

        assert not session_dir.exists()
        assert "Deleted preset ab12cd34" in capsys.readouterr().out

    def test_refuses_to_delete_a_running_creation(self, tmp_path, capsys):
        session_dir = self._session(tmp_path, status="running")

        with patch(
            "dstack._internal.cli.commands.preset.session_process_alive", return_value=True
        ):
            exit_code = run_dstack_cli(["preset", "delete", "ab12cd34", "-y"], home_dir=tmp_path)

        assert exit_code != 0
        assert "Preset creation is in use" in capsys.readouterr().out
        assert session_dir.exists()

    def test_refuses_to_delete_an_orphaned_creation_that_recorded_runs(self, tmp_path, capsys):
        # The agent died without stopping its runs: `runs.jsonl` is the only
        # record of them, so deleting it would strand them.
        session_dir = self._session(tmp_path, status="running")
        session_dir.joinpath("runs.jsonl").write_text('{"name": "qwen-1"}\n')

        exit_code = run_dstack_cli(["preset", "delete", "ab12cd34", "-y"], home_dir=tmp_path)

        assert exit_code != 0
        assert "Preset creation was interrupted" in capsys.readouterr().out
        assert session_dir.exists()

    def test_deletes_an_orphaned_creation_without_runs(self, tmp_path):
        session_dir = self._session(tmp_path, status="running")

        assert run_dstack_cli(["preset", "delete", "ab12cd34", "-y"], home_dir=tmp_path) == 0

        assert not session_dir.exists()

    def test_deletes_a_creation_whose_state_cannot_be_read(self, tmp_path):
        session_dir = tmp_path / ".dstack" / "presets" / "ab12cd34"
        session_dir.mkdir(parents=True)
        session_dir.joinpath("session.json").write_text("{")

        assert run_dstack_cli(["preset", "delete", "ab12cd34", "-y"], home_dir=tmp_path) == 0

        assert not session_dir.exists()

    @pytest.mark.skipif(IS_WINDOWS, reason="workspace alias symlinks are POSIX-only")
    def test_delete_removes_the_workspace_alias_but_nothing_outside_the_session(self, tmp_path):
        session_dir = self._session(tmp_path, status="interrupted")
        workspace = session_dir / "workspace"
        workspace.mkdir()
        alias = tmp_path / "dpe-alias"
        alias.symlink_to(workspace, target_is_directory=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        session_dir.joinpath("session.json").write_text(
            json.dumps(
                get_session_state(
                    status="interrupted",
                    run=get_session_run(
                        workspace=PresetSessionWorkspace(path=str(outside), alias=str(alias))
                    ),
                ).model_dump(mode="json")
            )
        )

        assert run_dstack_cli(["preset", "delete", "ab12cd34", "-y"], home_dir=tmp_path) == 0

        assert not session_dir.exists()
        # A dangling symlink is gone from exists() but still on disk.
        assert not alias.is_symlink()
        # The recorded path pointed outside the session, so it must survive.
        assert (outside / "keep.txt").read_text() == "keep"

    def _session(self, tmp_path, *, status: str):
        session_dir = tmp_path / ".dstack" / "presets" / "ab12cd34"
        session_dir.mkdir(parents=True)
        session_dir.joinpath("session.json").write_text(
            json.dumps(
                get_session_state(
                    status=status,
                    name="smoke",
                    run=get_session_run(
                        workspace=PresetSessionWorkspace(
                            path=str(session_dir / "workspace"),
                            alias=str(session_dir / "workspace"),
                        )
                    ),
                ).model_dump(mode="json")
            )
        )
        return session_dir

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
        assert data["submitted_at"] == render_datetime_as_api(preset.submitted_at)
        assert data["context_length"] == 32768
        assert data["benchmark"]["metrics"]["total_output_tokens"] == 2048

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
        assert data["submitted_at"] == render_datetime_as_api(preset.submitted_at)
        assert data["context_length"] == 32768
        assert data["benchmark"]["metrics"]["total_output_tokens"] == 2048

    @pytest.mark.parametrize("flag_attribute", [("--base", "base"), ("--repo", "model")])
    def test_deletes_all_presets_of_model_keeping_others_without_api_client(
        self, tmp_path, flag_attribute
    ):
        flag, attribute = flag_attribute
        preset = get_preset()
        store = PresetStore(tmp_path / ".dstack" / "presets")
        store.save(preset)
        store.save(preset.model_copy(update={"id": "01234567"}))
        # A preset of a different model must survive the delete.
        store.save(
            preset.model_copy(
                update={"id": "89abcdef", "base": "meta/Llama-4", "model": "meta/Llama-4"}
            )
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
            preset.model_copy(
                update={"id": "01234567", "base": "meta/Llama-4", "model": "meta/Llama-4"}
            )
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
        (corrupt_dir / "preset.yml").write_text("{not valid yaml")

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
base: Qwen/Qwen3.5-27B
regions: [file-region]
max_price: 0.5
trials: 1
concurrency: 8
max_ttft: 5000
min_context_length: 8192
env:
  - HF_TOKEN
"""
        )
        preset = get_preset()
        result = SimpleNamespace(
            preset=preset,
            path=tmp_path / "preset.yml",
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

    def test_create_detaches_the_name_from_the_old_preset(self, tmp_path):
        preset = get_preset().model_copy(update={"name": "qwen"})
        store = PresetStore(tmp_path / ".dstack" / "presets")
        store.save(preset)
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nname: qwen\nbase: Qwen/Qwen3.5-27B\ntrials: 1\nconcurrency: 8\nmax_ttft: 5000\nmin_context_length: 8192\n"
        )
        result = SimpleNamespace(
            preset=preset, path=tmp_path / "preset.yml", final_run_name="qwen-1"
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
        preset = get_preset().model_copy(update={"name": "qwen"})
        store = PresetStore(tmp_path / ".dstack" / "presets")
        store.save(preset)
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nname: qwen\nbase: Qwen/Qwen3.5-27B\ntrials: 1\nconcurrency: 8\nmax_ttft: 5000\nmin_context_length: 8192\n"
        )

        with (
            _patched_create_preset() as create,
            patch(
                "dstack._internal.cli.services.configurators.preset.confirm_ask",
                return_value=False,
            ),
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
        preset = get_preset().model_copy(update={"name": "qwen"})
        PresetStore(tmp_path / ".dstack" / "presets").save(preset)

        assert run_dstack_cli(["preset", "get", "qwen", "--json"], home_dir=tmp_path) == 0
        assert json.loads(capsys.readouterr().out)["id"] == preset.id

        assert run_dstack_cli(["preset", "delete", "qwen", "-y"], home_dir=tmp_path) == 0
        assert PresetStore(tmp_path / ".dstack" / "presets").list() == []

    def test_create_always_asks_even_without_a_name_conflict(self, tmp_path):
        configuration_path = tmp_path / "preset.dstack.yml"
        configuration_path.write_text(
            "type: preset\nbase: Qwen/Qwen3.5-27B\ntrials: 1\nconcurrency: 8\nmax_ttft: 5000\nmin_context_length: 8192\n"
        )

        with (
            _patched_create_preset() as create,
            patch(
                "dstack._internal.cli.services.configurators.preset.confirm_ask",
                return_value=False,
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


class TestApplyPresetConfiguration:
    _CONFIGURATION = """type: preset
name: file-name
base: Qwen/Qwen3.5-27B
trials: 1
concurrency: 8
max_ttft: 5000
min_context_length: 8192
"""

    def _write_configuration(self, tmp_path):
        path = tmp_path / "preset.dstack.yml"
        path.write_text(self._CONFIGURATION)
        return path

    def test_creates_the_preset(self, tmp_path):
        configuration_path = self._write_configuration(tmp_path)

        with _patched_create_preset() as create:
            exit_code = run_dstack_cli(
                ["apply", "-y", "-f", str(configuration_path)],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 0
        configuration = create.call_args.kwargs["configuration"]
        assert configuration.name == "file-name"
        assert configuration.model.base == "Qwen/Qwen3.5-27B"

    def test_accepts_creation_and_profile_arguments(self, tmp_path):
        configuration_path = self._write_configuration(tmp_path)

        with _patched_create_preset() as create:
            exit_code = run_dstack_cli(
                [
                    "apply",
                    "-y",
                    "-f",
                    str(configuration_path),
                    "--name",
                    "cli-name",
                    "--trials",
                    "7",
                    "--backend",
                    "gcp",
                    "--debug",
                ],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 0
        configuration = create.call_args.kwargs["configuration"]
        assert configuration.name == "cli-name"
        assert configuration.trials == 7
        assert configuration.backends == ["gcp"]
        assert create.call_args.kwargs["debug"] is True

    def test_rejects_detach(self, tmp_path, capsys):
        configuration_path = self._write_configuration(tmp_path)

        with _patched_create_preset() as create:
            exit_code = run_dstack_cli(
                ["apply", "-y", "-d", "-f", str(configuration_path)],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 1
        create.assert_not_called()
        captured = capsys.readouterr()
        assert "--detach" in captured.out + captured.err

    def test_rejects_unknown_arguments(self, tmp_path, capsys):
        configuration_path = self._write_configuration(tmp_path)

        with _patched_create_preset() as create:
            exit_code = run_dstack_cli(
                ["apply", "-y", "-f", str(configuration_path), "--nonsense"],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 1
        create.assert_not_called()
        captured = capsys.readouterr()
        assert "Unrecognized arguments: --nonsense" in captured.out + captured.err
