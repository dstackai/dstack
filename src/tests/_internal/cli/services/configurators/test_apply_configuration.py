from pathlib import Path

import pytest

from dstack._internal.cli.services.configurators import load_apply_configuration
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import TaskConfiguration

CONFIG_YAML = "type: task\ncommands:\n  - echo hi\n"


def write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CONFIG_YAML)
    return path


def chdir_work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    work_dir = tmp_path / "work"
    work_dir.mkdir(exist_ok=True)
    monkeypatch.chdir(work_dir)
    return work_dir


class TestLoadApplyConfiguration:
    def test_configuration_outside_cwd_is_returned_as_absolute_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        config_path = write_config(tmp_path / "conf" / ".dstack.yml")
        chdir_work_dir(tmp_path, monkeypatch)

        path, conf = load_apply_configuration(str(config_path))

        assert isinstance(conf, TaskConfiguration)
        assert conf.commands == ["echo hi"]
        assert Path(path).is_absolute()
        assert Path(path) == config_path

    def test_configuration_inside_cwd_is_returned_as_relative_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        write_config(tmp_path / "work" / "conf" / ".dstack.yml")
        chdir_work_dir(tmp_path, monkeypatch)

        path, conf = load_apply_configuration(str(Path("conf") / ".dstack.yml"))

        assert isinstance(conf, TaskConfiguration)
        assert path == str(Path("conf") / ".dstack.yml")

    def test_relative_path_with_parent_segments_stays_relative(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        write_config(tmp_path / "conf" / ".dstack.yml")
        chdir_work_dir(tmp_path, monkeypatch)

        path, conf = load_apply_configuration(str(Path("..") / "conf" / ".dstack.yml"))

        assert isinstance(conf, TaskConfiguration)
        assert path == str(Path("..") / "conf" / ".dstack.yml")

    def test_missing_configuration_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        chdir_work_dir(tmp_path, monkeypatch)

        with pytest.raises(ConfigurationError):
            load_apply_configuration(str(tmp_path / "missing.yml"))
