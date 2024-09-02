import argparse
import time
from pathlib import Path
from typing import List, Optional

from dstack._internal.cli.services.configurators.base import (
    ApplyEnvVarsConfiguratorMixin,
    BaseApplyConfigurator,
)
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.fleet import print_fleets_table
from dstack._internal.core.errors import ConfigurationError, ResourceNotExistsError
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.fleets import FleetConfiguration, FleetSpec
from dstack._internal.core.models.instances import SSHKey
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import convert_pkcs8_to_pem, generate_public_key, pkey_from_str
from dstack.api.utils import load_profile

logger = get_logger(__name__)


class FleetConfigurator(ApplyEnvVarsConfiguratorMixin, BaseApplyConfigurator):
    TYPE: ApplyConfigurationType = ApplyConfigurationType.FLEET

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        cls.register_env_args(parser)

    def apply_configuration(
        self,
        conf: FleetConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
        unknown_args: List[str],
    ):
        self.apply_args(conf, configurator_args, unknown_args)
        profile = load_profile(Path.cwd(), None)
        spec = FleetSpec(
            configuration=conf,
            profile=profile,
        )
        _preprocess_spec(spec)
        confirmed = False
        if conf.name is not None:
            try:
                fleet = self.api.client.fleets.get(
                    project_name=self.api.project,
                    name=conf.name,
                )
            except ResourceNotExistsError:
                pass
            else:
                if fleet.spec.configuration == conf:
                    if not command_args.force:
                        console.print(
                            "Fleet configuration has not changed. Use --force to recreate the fleet."
                        )
                        return
                    if not command_args.yes and not confirm_ask(
                        "Fleet configuration has not changed. Re-create the fleet?"
                    ):
                        console.print("\nExiting...")
                        return
                elif not command_args.yes and not confirm_ask(
                    f"Fleet [code]{conf.name}[/] already exists. Re-create the fleet?"
                ):
                    console.print("\nExiting...")
                    return
                confirmed = True
                with console.status("Deleting fleet..."):
                    self.api.client.fleets.delete(project_name=self.api.project, names=[conf.name])
                    # Fleet deletion is async. Wait for fleet to be deleted.
                    while True:
                        try:
                            self.api.client.fleets.get(
                                project_name=self.api.project, name=conf.name
                            )
                        except ResourceNotExistsError:
                            break
                        else:
                            time.sleep(1)
        if not confirmed and not command_args.yes:
            confirm_message = "Configuration does not specify the fleet name. Create a new fleet?"
            if conf.name is not None:
                confirm_message = (
                    f"Fleet [code]{conf.name}[/] does not exist yet. Create the fleet?"
                )
            if not confirm_ask(confirm_message):
                console.print("\nExiting...")
                return
        with console.status("Creating fleet..."):
            fleet = self.api.client.fleets.create(
                project_name=self.api.project,
                spec=spec,
            )
        print_fleets_table([fleet])

    def delete_configuration(
        self,
        conf: FleetConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
    ):
        if conf.name is None:
            console.print("[error]Configuration specifies no fleet to delete[/]")
            exit(1)

        try:
            self.api.client.fleets.get(
                project_name=self.api.project,
                name=conf.name,
            )
        except ResourceNotExistsError:
            console.print(f"Fleet [code]{conf.name}[/] does not exist")
            exit(1)

        if not command_args.yes and not confirm_ask(f"Delete the fleet [code]{conf.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting fleet..."):
            self.api.client.fleets.delete(project_name=self.api.project, names=[conf.name])
            # Fleet deletion is async. Wait for fleet to be deleted.
            while True:
                try:
                    self.api.client.fleets.get(project_name=self.api.project, name=conf.name)
                except ResourceNotExistsError:
                    break
                else:
                    time.sleep(1)

        console.print(f"Fleet [code]{conf.name}[/] deleted")

    def apply_args(self, conf: FleetConfiguration, args: argparse.Namespace, unknown: List[str]):
        self.apply_env_vars(conf.env, args)
        if conf.ssh_config is None and conf.env:
            raise ConfigurationError("`env` is currently supported for on-prem fleets only")


def _preprocess_spec(spec: FleetSpec):
    if spec.configuration.ssh_config is not None:
        spec.configuration.ssh_config.ssh_key = _resolve_ssh_key(
            spec.configuration.ssh_config.identity_file
        )
        for host in spec.configuration.ssh_config.hosts:
            if not isinstance(host, str):
                host.ssh_key = _resolve_ssh_key(host.identity_file)


def _resolve_ssh_key(ssh_key_path: Optional[str]) -> Optional[SSHKey]:
    if ssh_key_path is None:
        return None
    ssh_key_path_obj = Path(ssh_key_path).expanduser()
    try:
        private_key = convert_pkcs8_to_pem(ssh_key_path_obj.read_text())
        try:
            pub_key = ssh_key_path_obj.with_suffix(".pub").read_text()
        except FileNotFoundError:
            pub_key = generate_public_key(pkey_from_str(private_key))
        return SSHKey(public=pub_key, private=private_key)
    except OSError as e:
        logger.debug("Got OSError: %s", repr(e))
        console.print(f"[error]Unable to read the SSH key at {ssh_key_path}[/]")
        exit()
    except ValueError as e:
        logger.debug("Key type is not supported", repr(e))
        console.print("[error]Key type is not supported[/]")
        exit()
