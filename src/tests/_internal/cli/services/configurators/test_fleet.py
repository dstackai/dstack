import argparse
from datetime import datetime, timezone
from textwrap import dedent
from typing import List, Optional, Tuple
from unittest.mock import Mock
from uuid import uuid4

import pytest
from rich.console import Console

import dstack._internal.cli.services.configurators.fleet as fleet_configurator_module
from dstack._internal.cli.services.configurators.fleet import (
    FleetConfigurator,
    _render_fleet_spec_diff,
)
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.fleets import (
    Fleet,
    FleetConfiguration,
    FleetNodesSpec,
    FleetPlan,
    FleetSpec,
    FleetStatus,
    InstanceGroupPlacement,
)
from dstack._internal.core.models.profiles import Profile


def create_conf() -> FleetConfiguration:
    return FleetConfiguration.parse_obj({"ssh_config": {"hosts": ["1.2.3.4"]}})


def apply_args(
    conf: FleetConfiguration, args: List[str]
) -> Tuple[FleetConfiguration, argparse.Namespace]:
    parser = argparse.ArgumentParser()
    configurator = FleetConfigurator(Mock())
    configurator.register_args(parser)
    conf = conf.copy(deep=True)
    configurator_args = parser.parse_args(args)
    configurator.apply_args(conf, configurator_args)
    return conf, configurator_args


def get_cloud_fleet_spec(
    *,
    name: str = "test-fleet",
    nodes: Optional[FleetNodesSpec] = None,
    placement: Optional[InstanceGroupPlacement] = None,
) -> FleetSpec:
    if nodes is None:
        nodes = FleetNodesSpec(min=0, target=0, max=1)
    return FleetSpec(
        configuration=FleetConfiguration(
            name=name,
            nodes=nodes,
            placement=placement,
        ),
        configuration_path="fleet.dstack.yml",
        profile=Profile(),
    )


def get_ssh_fleet_spec(
    *,
    name: str = "test-fleet",
    hosts: Optional[list[str]] = None,
) -> FleetSpec:
    if hosts is None:
        hosts = ["10.0.0.100"]
    return FleetSpec(
        configuration=FleetConfiguration.parse_obj(
            {
                "name": name,
                "ssh_config": {"hosts": hosts},
            }
        ),
        configuration_path="fleet.dstack.yml",
        profile=Profile(),
    )


def create_fleet_plan(
    *,
    current_spec: FleetSpec,
    spec: FleetSpec,
    action: ApplyAction,
) -> FleetPlan:
    return FleetPlan(
        project_name="test-project",
        user="test-user",
        spec=spec,
        effective_spec=spec,
        current_resource=Fleet(
            id=uuid4(),
            name=current_spec.configuration.name or "test-fleet",
            project_name="test-project",
            spec=current_spec,
            created_at=datetime.now(timezone.utc),
            status=FleetStatus.ACTIVE,
            instances=[],
        ),
        offers=[],
        total_offers=0,
        action=action,
    )


def get_command_args() -> argparse.Namespace:
    return argparse.Namespace(
        yes=False,
        force=False,
        detach=False,
    )


def patch_console_and_confirm(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Console, Mock]:
    console = Console(record=True, force_terminal=False, color_system=None, width=120)
    confirm_ask = Mock(return_value=False)
    monkeypatch.setattr(fleet_configurator_module, "console", console)
    monkeypatch.setattr(fleet_configurator_module, "confirm_ask", confirm_ask)
    return console, confirm_ask


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


class TestApplyPlanMessages:
    def test_prints_in_place_update_diff(self, monkeypatch: pytest.MonkeyPatch):
        console, confirm_ask = patch_console_and_confirm(monkeypatch)
        current_spec = get_cloud_fleet_spec(nodes=FleetNodesSpec(min=0, target=0, max=1))
        spec = get_cloud_fleet_spec(nodes=FleetNodesSpec(min=1, target=1, max=1))
        plan = create_fleet_plan(
            current_spec=current_spec,
            spec=spec,
            action=ApplyAction.UPDATE,
        )

        FleetConfigurator(Mock())._apply_plan(plan, get_command_args())

        output = console.export_text()
        assert "Found fleet test-fleet." in output
        assert "Detected changes that can be updated in-place:" in output
        assert "- Configuration properties:" in output
        assert "  - nodes" in output
        confirm_ask.assert_called_once_with("Update the fleet in-place?")

    def test_prints_recreate_diff(self, monkeypatch: pytest.MonkeyPatch):
        console, confirm_ask = patch_console_and_confirm(monkeypatch)
        current_spec = get_cloud_fleet_spec(placement=InstanceGroupPlacement.ANY)
        spec = get_cloud_fleet_spec(placement=InstanceGroupPlacement.CLUSTER)
        plan = create_fleet_plan(
            current_spec=current_spec,
            spec=spec,
            action=ApplyAction.CREATE,
        )

        FleetConfigurator(Mock())._apply_plan(plan, get_command_args())

        output = console.export_text()
        assert "Found fleet test-fleet." in output
        assert "Detected changes that cannot be updated in-place:" in output
        assert "- Configuration properties:" in output
        assert "  - placement" in output
        confirm_ask.assert_called_once_with("Re-create the fleet?")

    def test_prints_no_diff_message(self, monkeypatch: pytest.MonkeyPatch):
        console, confirm_ask = patch_console_and_confirm(monkeypatch)
        spec = get_cloud_fleet_spec()
        plan = create_fleet_plan(
            current_spec=spec,
            spec=spec.copy(deep=True),
            action=ApplyAction.UPDATE,
        )

        FleetConfigurator(Mock())._apply_plan(plan, get_command_args())

        output = console.export_text()
        assert "Found fleet test-fleet." in output
        assert "No configuration changes detected." in output
        assert "Detected changes that" not in output
        confirm_ask.assert_called_once_with("Re-create the fleet?")


class TestRenderFleetSpecDiff:
    def test_renders_cloud_nodes_change(self):
        old = get_cloud_fleet_spec(nodes=FleetNodesSpec(min=0, target=0, max=1))
        new = get_cloud_fleet_spec(nodes=FleetNodesSpec(min=1, target=1, max=1))

        assert (
            _render_fleet_spec_diff(old, new)
            == dedent(
                """
                - Configuration properties:
                  - nodes
                """
            ).lstrip()
        )

    def test_renders_ssh_hosts_change(self):
        old = get_ssh_fleet_spec(hosts=["10.0.0.100"])
        new = get_ssh_fleet_spec(hosts=["10.0.0.100", "10.0.0.101"])

        assert (
            _render_fleet_spec_diff(old, new)
            == dedent(
                """
                - Configuration properties:
                  - ssh_config
                """
            ).lstrip()
        )

    def test_no_diff(self):
        spec = get_cloud_fleet_spec()

        assert _render_fleet_spec_diff(spec, spec.copy(deep=True)) is None
