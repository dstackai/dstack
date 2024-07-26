import argparse
from typing import List, Tuple
from unittest.mock import Mock

import pytest

from dstack._internal.cli.services.configurators import get_run_configurator_class
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import (
    BaseRunConfiguration,
    PortMapping,
    TaskConfiguration,
)


class TestRunConfigurator:
    def test_env(self):
        conf = TaskConfiguration(commands=["whoami"])
        modified, args = apply_args(conf, ["-e", "A=1", "--env", "B=2"])
        conf.env = {"A": "1", "B": "2"}
        assert modified.dict() == conf.dict()

    def test_ports(self):
        conf = TaskConfiguration(commands=["whoami"])
        modified, args = apply_args(conf, ["-p", "80", "--port", "8080"])
        conf.ports = [
            PortMapping(local_port=80, container_port=80),
            PortMapping(local_port=8080, container_port=8080),
        ]
        assert modified.dict() == conf.dict()

    def test_container_ports_conflict(self):
        conf = TaskConfiguration(commands=["whoami"])
        with pytest.raises(ConfigurationError):
            apply_args(conf, ["-p", "8000:80", "--port", "8001:80"])

    def test_env_override(self):
        conf = TaskConfiguration(commands=["whoami"], env={"A": "0"})
        modified, args = apply_args(conf, ["-e", "A=1", "--env", "B=2"])
        conf.env = {"A": "1", "B": "2"}
        assert modified.dict() == conf.dict()

    def test_ports_override(self):
        conf = TaskConfiguration(commands=["whoami"], ports=["80"])
        modified, args = apply_args(conf, ["-p", "8000:80", "--port", "8001:8000"])
        conf.ports = [
            PortMapping(local_port=8000, container_port=80),
            PortMapping(local_port=8001, container_port=8000),
        ]
        assert modified.dict() == conf.dict()

    def test_local_ports_conflict(self):
        conf = TaskConfiguration(commands=["whoami"], ports=["3000"])
        with pytest.raises(ConfigurationError):
            apply_args(conf, ["-p", "3000:4000"])

    def test_any_port(self):
        conf = TaskConfiguration(commands=["whoami"], ports=["8000"])
        modified, args = apply_args(conf, ["-p", "*:8000"])
        conf.ports = [PortMapping(local_port=None, container_port=8000)]
        assert modified.dict() == conf.dict()


def apply_args(
    conf: BaseRunConfiguration, args: List[str]
) -> Tuple[BaseRunConfiguration, argparse.Namespace]:
    parser = argparse.ArgumentParser()
    configurator_class = get_run_configurator_class(conf.type)
    configurator = configurator_class(Mock())
    configurator.register_args(parser)
    conf = conf.copy(deep=True)  # to avoid modifying the original configuration
    known, unknown = parser.parse_known_args(args)
    configurator.apply_args(conf, known, unknown)
    return conf, known
