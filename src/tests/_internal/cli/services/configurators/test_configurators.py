from pathlib import Path

import pytest

from dstack._internal.cli.services.configurators import load_apply_configuration
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import TaskConfiguration

CONFIGURATION_YAML = "type: task\ncommands:\n  - echo hi\n"


class TestLoadApplyConfiguration:
    @pytest.fixture
    def cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        return cwd

    def test_returns_relative_path_for_configuration_under_cwd(self, cwd: Path):
        _write_configuration(cwd / "conf" / "task.dstack.yml")

        path, conf = load_apply_configuration(str(cwd / "conf" / "task.dstack.yml"))

        assert path == str(Path("conf") / "task.dstack.yml")
        assert isinstance(conf, TaskConfiguration)

    def test_returns_absolute_path_for_configuration_outside_cwd(self, cwd: Path):
        configuration_path = _write_configuration(cwd.parent / "conf" / "task.dstack.yml")

        path, conf = load_apply_configuration(str(configuration_path))

        assert path == str(configuration_path)
        assert isinstance(conf, TaskConfiguration)

    def test_keeps_parent_segments_of_relative_path(self, cwd: Path):
        _write_configuration(cwd.parent / "conf" / "task.dstack.yml")
        configuration_file = str(Path("..") / "conf" / "task.dstack.yml")

        path, _ = load_apply_configuration(configuration_file)

        assert path == configuration_file

    def test_loads_default_configuration_from_cwd(self, cwd: Path):
        _write_configuration(cwd / ".dstack.yml")

        path, conf = load_apply_configuration(None)

        assert path == ".dstack.yml"
        assert isinstance(conf, TaskConfiguration)

    def test_raises_if_configuration_does_not_exist(self, cwd: Path):
        with pytest.raises(ConfigurationError):
            load_apply_configuration(str(cwd / "missing.dstack.yml"))


def _write_configuration(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CONFIGURATION_YAML)
    return path
