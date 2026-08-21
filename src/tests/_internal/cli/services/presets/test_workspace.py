import pytest

from dstack._internal.cli.services.presets.session import PresetSession
from dstack._internal.cli.services.presets.workspace import (
    PresetAgentWorkspace,
    install_previous_records,
)

pytestmark = pytest.mark.windows


def _previous_session(tmp_path, preset_id="8d3b01aa"):
    root = tmp_path / "store" / preset_id
    (root / "trials" / "1" / "patches").mkdir(parents=True)
    (root / "trials" / "1" / "trial.json").write_text('{"learned": "x"}')
    (root / "trials" / "1" / "task.dstack.yml").write_text("type: task\n")
    (root / "trials" / "1" / "patches" / "moe.py.patch").write_text("--- a\n+++ b\n")
    (root / "service" / "1").mkdir(parents=True)
    (root / "service" / "1" / "service.dstack.yml").write_text("type: service\n")
    (root / "service" / "1" / "verification.json").write_text('{"status": "verified"}')
    (root / "constraints.json").write_text("{}")
    (root / "final_report.json").write_text('{"success": true}')
    # Everything below must stay out of the copy.
    (root / "session.json").write_text("{}")
    (root / "agent.log").write_text("log")
    (root / "trace.jsonl").write_text("{}")
    (root / "runs.jsonl").write_text("{}")
    (root / "trials" / "not-a-trial").mkdir()
    (root / "trials" / "not-a-trial" / "trial.json").write_text("{}")
    return PresetSession(path=root, preset_id=preset_id)


def _workspace(tmp_path):
    path = tmp_path / "workspace" / "w"
    path.mkdir(parents=True)
    return PresetAgentWorkspace(path=path, dstack_home=tmp_path / "workspace" / "h")


class TestInstallPreviousRecords:
    def test_copies_exactly_the_record_subset(self, tmp_path):
        session = _previous_session(tmp_path)
        workspace = _workspace(tmp_path)

        install_previous_records(workspace, [session])

        target = workspace.path / "previous" / "8d3b01aa"
        copied = sorted(
            file.relative_to(target).as_posix() for file in target.rglob("*") if file.is_file()
        )
        assert copied == [
            "constraints.json",
            "final_report.json",
            "service/1/service.dstack.yml",
            "service/1/verification.json",
            "trials/1/patches/moe.py.patch",
            "trials/1/task.dstack.yml",
            "trials/1/trial.json",
        ]

    def test_recopy_removes_stale_files(self, tmp_path):
        session = _previous_session(tmp_path)
        workspace = _workspace(tmp_path)
        install_previous_records(workspace, [session])
        stale = workspace.path / "previous" / "8d3b01aa" / "trials" / "9" / "trial.json"
        stale.parent.mkdir(parents=True)
        stale.write_text("{}")

        install_previous_records(workspace, [session])

        assert not stale.exists()
        assert (workspace.path / "previous" / "8d3b01aa" / "trials" / "1" / "trial.json").exists()

    def test_a_session_without_records_warns(self, tmp_path, capsys):
        root = tmp_path / "store" / "empty000"
        root.mkdir(parents=True)
        (root / "session.json").write_text("{}")
        session = PresetSession(path=root, preset_id="empty000")
        workspace = _workspace(tmp_path)

        install_previous_records(workspace, [session])

        assert "empty000 has no records" in capsys.readouterr().out
        assert not (workspace.path / "previous" / "empty000").exists()
