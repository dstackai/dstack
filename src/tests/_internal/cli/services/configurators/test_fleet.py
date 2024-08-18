import argparse
from typing import List, Tuple
from unittest.mock import Mock

import pytest

from dstack._internal.cli.services.configurators.fleet import FleetConfigurator
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.fleets import FleetConfiguration


class TestFleetConfigurator:
    def test_env(self):
        conf = create_conf()
        modified, args = apply_args(conf, ["-e", "A=1", "--env", "B=2"])
        conf.env = Env.parse_obj({"A": "1", "B": "2"})
        assert modified.dict() == conf.dict()

    def test_env_override(self):
        conf = create_conf()
        conf.env = Env.parse_obj({"A": "0"})
        modified, args = apply_args(conf, ["-e", "A=1", "--env", "B=2"])
        conf.env = Env.parse_obj({"A": "1", "B": "2"})
        assert modified.dict() == conf.dict()

    def test_env_value_from_environ(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FROM_ENV", "2")
        conf = create_conf()
        conf.env = Env.parse_obj({"FROM_CONF": "1"})
        modified, args = apply_args(conf, ["--env", "FROM_ENV"])
        conf.env = Env.parse_obj({"FROM_CONF": "1", "FROM_ENV": "2"})
        assert modified.dict() == conf.dict()

    def test_env_value_from_environ_not_set(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FROM_ENV", raising=False)
        conf = create_conf()
        with pytest.raises(ConfigurationError, match=r"FROM_ENV is not set"):
            apply_args(conf, ["--env", "FROM_ENV"])


def create_conf() -> FleetConfiguration:
    return FleetConfiguration.parse_obj({"ssh_config": {"hosts": ["1.2.3.4"]}})


def apply_args(
    conf: FleetConfiguration, args: List[str]
) -> Tuple[FleetConfiguration, argparse.Namespace]:
    parser = argparse.ArgumentParser()
    configurator = FleetConfigurator(Mock())
    configurator.register_args(parser)
    conf = conf.copy(deep=True)
    configurator_args, unknown_args = parser.parse_known_args(args)
    configurator.apply_args(conf, configurator_args, unknown_args)
    return conf, configurator_args
