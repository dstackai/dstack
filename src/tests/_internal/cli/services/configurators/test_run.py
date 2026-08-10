import argparse
from textwrap import dedent
from typing import List, Tuple
from unittest.mock import Mock

import pytest
from gpuhunt import KNOWN_TENSTORRENT_ACCELERATORS

from dstack._internal.cli.services.configurators import get_run_configurator_class
from dstack._internal.cli.services.configurators.run import (
    ServiceConfigurator,
    render_run_spec_diff,
)
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.configurations import (
    BaseRunConfiguration,
    DevEnvironmentConfiguration,
    PortMapping,
    TaskConfiguration,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.profiles import Profile
from dstack._internal.server.testing.common import get_run_spec

_TENSTORRENT_ACCELERATOR_NAMES = tuple(
    sorted({gpu.name for gpu in KNOWN_TENSTORRENT_ACCELERATORS})
)


class TestApplyArgs:
    def apply_args(
        self, conf: BaseRunConfiguration, args: List[str]
    ) -> Tuple[BaseRunConfiguration, argparse.Namespace]:
        parser = argparse.ArgumentParser()
        configurator_class = get_run_configurator_class(conf.type)
        configurator = configurator_class(Mock())
        configurator.register_args(parser)
        conf = conf.model_copy(deep=True)  # to avoid modifying the original configuration
        parsed_args = parser.parse_args(args)
        configurator.apply_args(conf, parsed_args)
        return conf, parsed_args

    def test_env(self):
        conf = TaskConfiguration(commands=["whoami"])
        modified, args = self.apply_args(conf, ["-e", "A=1", "--env", "B=2"])
        conf.env = Env.model_validate({"A": "1", "B": "2"})
        assert modified.model_dump() == conf.model_dump()

    def test_ports(self):
        conf = TaskConfiguration(commands=["whoami"])
        modified, args = self.apply_args(conf, ["-p", "80", "--port", "8080"])
        conf.ports = [
            PortMapping(local_port=80, container_port=80),
            PortMapping(local_port=8080, container_port=8080),
        ]
        assert modified.model_dump() == conf.model_dump()

    def test_container_ports_conflict(self):
        conf = TaskConfiguration(commands=["whoami"])
        with pytest.raises(ConfigurationError):
            self.apply_args(conf, ["-p", "8000:80", "--port", "8001:80"])

    def test_env_override(self):
        conf = TaskConfiguration(commands=["whoami"], env=Env.model_validate({"A": "0"}))
        modified, args = self.apply_args(conf, ["-e", "A=1", "--env", "B=2"])
        conf.env = Env.model_validate({"A": "1", "B": "2"})
        assert modified.model_dump() == conf.model_dump()

    def test_ports_override(self):
        conf = TaskConfiguration(commands=["whoami"], ports=["80"])
        modified, args = self.apply_args(conf, ["-p", "8000:80", "--port", "8001:8000"])
        conf.ports = [
            PortMapping(local_port=8000, container_port=80),
            PortMapping(local_port=8001, container_port=8000),
        ]
        assert modified.model_dump() == conf.model_dump()

    def test_local_ports_conflict(self):
        conf = TaskConfiguration(commands=["whoami"], ports=["3000"])
        with pytest.raises(ConfigurationError):
            self.apply_args(conf, ["-p", "3000:4000"])

    def test_any_port(self):
        conf = TaskConfiguration(commands=["whoami"], ports=["8000"])
        modified, args = self.apply_args(conf, ["-p", "*:8000"])
        conf.ports = [PortMapping(local_port=None, container_port=8000)]
        assert modified.model_dump() == conf.model_dump()

    def test_interpolates_env(self):
        conf = TaskConfiguration(
            image="my_image",
            registry_auth=RegistryAuth(
                username="${{ env.REGISTRY_USERNAME }}",
                password="${{ env.REGISTRY_PASSWORD }}",
            ),
            env=Env.model_validate(
                {
                    "REGISTRY_USERNAME": "test_user",
                    "REGISTRY_PASSWORD": "test_password",
                }
            ),
        )
        modified, args = self.apply_args(conf, [])
        assert modified.registry_auth == RegistryAuth(
            username="test_user",
            password="test_password",
        )


class TestApplyConfiguration:
    def test_composes_get_plan_and_apply_plan(self, monkeypatch):
        run_plan, repo = Mock(), Mock()
        get_plan = Mock(return_value=(run_plan, repo))
        apply_plan = Mock(return_value=object())
        monkeypatch.setattr(ServiceConfigurator, "get_plan", get_plan)
        monkeypatch.setattr(ServiceConfigurator, "apply_plan", apply_plan)
        conf, command_args, configurator_args = Mock(), Mock(), Mock()

        result = ServiceConfigurator(api_client=Mock()).apply_configuration(
            conf, "svc.dstack.yml", command_args, configurator_args
        )

        assert result is None
        get_plan.assert_called_once_with(
            conf=conf,
            configuration_path="svc.dstack.yml",
            configurator_args=configurator_args,
        )
        apply_plan.assert_called_once_with(
            run_plan=run_plan,
            repo=repo,
            command_args=command_args,
            configurator_args=configurator_args,
        )


class TestRenderRunSpecDiff:
    def test_diff(self):
        old = get_run_spec(
            run_name="test",
            repo_id="test-1",
            configuration_path="1.dstack.yml",
            profile=Profile(
                backends=[BackendType.AWS],
                regions=["us-west-1"],
                name="test",
                default=True,
            ),
            configuration=DevEnvironmentConfiguration(
                name="test",
                ide="vscode",
                inactivity_duration=60,
            ),
        )
        new = get_run_spec(
            run_name="test",
            repo_id="test-2",
            configuration_path="2.dstack.yml",
            profile=Profile(
                backends=[BackendType.AWS],
                regions=["us-west-2"],
                name="test",
                default=True,
            ),
            configuration=DevEnvironmentConfiguration(
                name="test",
                ide="cursor",
                inactivity_duration=None,
            ),
        )
        assert (
            render_run_spec_diff(old, new)
            == dedent(
                """
                - Repo ID
                - Configuration path
                - Configuration properties:
                  - ide
                  - inactivity_duration
                - Profile properties:
                  - regions
                """
            ).lstrip()
        )

    def test_field_type_change(self):
        old = get_run_spec(
            run_name="test",
            repo_id="test",
            profile=Profile(name="test"),
            configuration=DevEnvironmentConfiguration(
                name="test",
                ide="vscode",
            ),
        )
        new = get_run_spec(
            run_name="test",
            repo_id="test",
            profile=None,
            configuration=TaskConfiguration(
                name="test",
                commands=["sleep infinity"],
            ),
        )
        assert (
            render_run_spec_diff(old, new)
            == dedent(
                """
                - Configuration type
                - Profile
                """
            ).lstrip()
        )

    def test_no_diff(self):
        old = get_run_spec(run_name="test", repo_id="test")
        new = get_run_spec(run_name="test", repo_id="test")
        assert render_run_spec_diff(old, new) is None
