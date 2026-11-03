import argparse
from datetime import datetime, timezone
from pathlib import Path
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
    _resolve_ssh_key,
)
from dstack._internal.core.errors import CLIError, ConfigurationError
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
    SSHHostParams,
    SSHProxyParams,
)
from dstack._internal.core.models.instances import SSHKey
from dstack._internal.core.models.profiles import Profile
from tests._internal.utils.test_ssh import PRIVATE_KEY, PUBLIC_KEY, PUBLIC_KEY_NO_COMMENT


def create_conf() -> FleetConfiguration:
    return FleetConfiguration.model_validate({"ssh_config": {"hosts": ["1.2.3.4"]}})


def apply_args(
    conf: FleetConfiguration, args: List[str]
) -> Tuple[FleetConfiguration, argparse.Namespace]:
    parser = argparse.ArgumentParser()
    configurator = FleetConfigurator(Mock())
    configurator.register_args(parser)
    conf = conf.model_copy(deep=True)
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
        configuration=FleetConfiguration.model_validate(
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
        conf.env = Env.model_validate({"A": "1", "B": "2"})
        assert modified.model_dump() == conf.model_dump()

    def test_env_override(self):
        conf = create_conf()
        conf.env = Env.model_validate({"A": "0"})
        modified, args = apply_args(conf, ["-e", "A=1", "--env", "B=2"])
        conf.env = Env.model_validate({"A": "1", "B": "2"})
        assert modified.model_dump() == conf.model_dump()

    def test_env_value_from_environ(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FROM_ENV", "2")
        conf = create_conf()
        conf.env = Env.model_validate({"FROM_CONF": "1"})
        modified, args = apply_args(conf, ["--env", "FROM_ENV"])
        conf.env = Env.model_validate({"FROM_CONF": "1", "FROM_ENV": "2"})
        assert modified.model_dump() == conf.model_dump()

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

    @pytest.mark.parametrize(
        "per_host,head_node,same_path",
        [(False, False, False), (False, True, True), (True, False, True), (True, True, False)],
    )
    def test_identifies_the_changed_ssh_key_without_printing_key_material(
        self, monkeypatch, per_host, head_node, same_path
    ):
        console, confirm_ask = patch_console_and_confirm(monkeypatch)
        current = get_ssh_fleet_spec()
        ssh = current.configuration.ssh_config
        assert ssh is not None
        target = ssh
        path = "ssh_config"
        if per_host:
            target = SSHHostParams(hostname="10.0.0.100")
            ssh.hosts = [target]
            path += ".hosts[0]"
        if head_node:
            jump = SSHProxyParams(hostname="head", user="ubuntu", identity_file="old-key")
            target.proxy_jump = jump
            target = jump
            path += ".proxy_jump"
        target.identity_file = "old-key"
        target.ssh_key = SSHKey(public="old-public-key", private="old-private-key")
        new = current.model_copy(deep=True)
        changed = new.configuration.ssh_config
        assert changed is not None
        if per_host:
            changed = changed.hosts[0]
            assert isinstance(changed, SSHHostParams)
        if head_node:
            changed = changed.proxy_jump
        assert changed is not None
        if not same_path:
            changed.identity_file = "new-key"
        changed.ssh_key = SSHKey(public="new-public-key", private="new-private-key")

        plan = create_fleet_plan(current_spec=current, spec=new, action=ApplyAction.UPDATE)
        FleetConfigurator(Mock())._apply_plan(plan, get_command_args())

        output = console.export_text()
        label = f"{path}.identity_file" + (" (key contents changed)" if same_path else "")
        assert f"  - {label}\n" in output
        assert "ssh_key" not in output
        assert "public-key" not in output
        assert "private-key" not in output
        confirm_ask.assert_called_once_with("Update the fleet in-place?")

    @pytest.mark.parametrize("field,value", [("user", "other-user"), ("port", 2222)])
    def test_identifies_ssh_route_changes_requiring_recreation(self, monkeypatch, field, value):
        console, confirm_ask = patch_console_and_confirm(monkeypatch)
        current = get_ssh_fleet_spec()
        new = current.model_copy(deep=True)
        assert new.configuration.ssh_config is not None
        setattr(new.configuration.ssh_config, field, value)
        plan = create_fleet_plan(current_spec=current, spec=new, action=ApplyAction.CREATE)

        FleetConfigurator(Mock())._apply_plan(plan, get_command_args())

        output = console.export_text()
        assert "Detected changes that cannot be updated in-place:" in output
        assert f"  - ssh_config.{field}\n" in output
        confirm_ask.assert_called_once_with("Re-create the fleet?")

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
            spec=spec.model_copy(deep=True),
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
                  - ssh_config.hosts
                """
            ).lstrip()
        )

    def test_no_diff(self):
        spec = get_cloud_fleet_spec()

        assert _render_fleet_spec_diff(spec, spec.model_copy(deep=True)) is None


class TestResolveSSHKey:
    def test_returns_none_if_no_path_given(self):
        assert _resolve_ssh_key(None) is None

    def test_uses_public_key_file(self, tmp_path: Path):
        private_key_path = tmp_path / "id_ed25519"
        private_key_path.write_text(PRIVATE_KEY)
        (tmp_path / "id_ed25519.pub").write_text(PUBLIC_KEY)

        assert _resolve_ssh_key(str(private_key_path)) == SSHKey(
            public=PUBLIC_KEY, private=PRIVATE_KEY
        )

    def test_generates_public_key(self, tmp_path: Path):
        private_key_path = tmp_path / "id_ed25519"
        private_key_path.write_text(PRIVATE_KEY)

        assert _resolve_ssh_key(str(private_key_path)) == SSHKey(
            public=PUBLIC_KEY_NO_COMMENT, private=PRIVATE_KEY
        )

    def test_raises_if_public_key_given(self, tmp_path: Path):
        public_key_path = tmp_path / "id_ed25519.pub"
        public_key_path.write_text(PUBLIC_KEY)

        with pytest.raises(CLIError, match="Expected a private key"):
            _resolve_ssh_key(str(public_key_path))

    def test_raises_if_key_does_not_exist(self, tmp_path: Path):
        with pytest.raises(CLIError, match="Unable to read the SSH key"):
            _resolve_ssh_key(str(tmp_path / "id_ed25519"))

    def test_raises_if_key_type_is_not_supported(self, tmp_path: Path):
        key_path = tmp_path / "id_ed25519"
        key_path.write_text("garbage")

        with pytest.raises(CLIError, match="Unsupported or invalid SSH key"):
            _resolve_ssh_key(str(key_path))
