import argparse
import re
import subprocess
from typing import Dict, List, Optional, Tuple, Type

from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import (
    BaseConfiguration,
    BaseConfigurationWithPorts,
    ConfigurationType,
    DevEnvironmentConfiguration,
    PortMapping,
)


class BaseRunConfigurator:
    TYPE: ConfigurationType = None

    @classmethod
    def register(cls, parser: argparse.ArgumentParser):
        parser.add_argument(
            "-e",
            "--env",
            type=env_var,
            action="append",
            help="Environment variables",
            dest="envs",
            metavar="KEY=VALUE",
        )

    @classmethod
    def apply(cls, args: argparse.Namespace, conf: BaseConfiguration):
        if args.envs:
            for k, v in args.envs:
                conf.env[k] = v


class RunWithPortsConfigurator(BaseRunConfigurator):
    @classmethod
    def register(cls, parser: argparse.ArgumentParser):
        super().register(parser)
        parser.add_argument(
            "-p",
            "--port",
            type=port_mapping,
            action="append",
            help="Exposed port or mapping",
            dest="ports",
            metavar="MAPPING",
        )

    @classmethod
    def apply(cls, args: argparse.Namespace, conf: BaseConfigurationWithPorts):
        super().apply(args, conf)
        if args.ports:
            conf.ports = list(merge_ports(conf.ports, args.ports).values())


class TaskRunConfigurator(RunWithPortsConfigurator):
    TYPE = ConfigurationType.TASK


class DevEnvironmentRunConfigurator(RunWithPortsConfigurator):
    TYPE = ConfigurationType.DEV_ENVIRONMENT

    @classmethod
    def apply(cls, args: argparse.Namespace, conf: DevEnvironmentConfiguration):
        super().apply(args, conf)
        if conf.ide == "vscode" and conf.version is None:
            conf.version = _detect_vscode_version()
            if conf.version is None:
                console.print(
                    "[secondary]Unable to detect the VS Code version and pre-install extensions. "
                    "Fix by opening [code]Command Palette[/code], executing [code]Shell Command: "
                    "Install 'code' command in PATH[/code], and restarting terminal.[/]\n"
                )


class ServiceRunConfigurator(BaseRunConfigurator):
    TYPE = ConfigurationType.SERVICE


def env_var(v: str) -> Tuple[str, str]:
    r = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)=(.*)$", v)
    if r is None:
        raise ValueError(v)
    key, value = r.groups()
    return key, value


def port_mapping(v: str) -> PortMapping:
    return PortMapping.parse(v)


def merge_ports(conf: List[PortMapping], args: List[PortMapping]) -> Dict[int, PortMapping]:
    unique_ports_constraint([pm.container_port for pm in conf])
    unique_ports_constraint([pm.container_port for pm in args])

    ports = {pm.container_port: pm for pm in conf}
    for pm in args:  # override conf
        ports[pm.container_port] = pm

    unique_ports_constraint([pm.local_port for pm in ports.values() if pm.local_port is not None])
    return ports


def unique_ports_constraint(ports: List[int]):
    used_ports = set()
    for i in ports:
        if i in used_ports:
            raise ConfigurationError(f"Port {i} is already in use")
        used_ports.add(i)


def _detect_vscode_version(exe: str = "code") -> Optional[str]:
    try:
        run = subprocess.run([exe, "--version"], capture_output=True)
    except FileNotFoundError:
        return None
    if run.returncode == 0:
        return run.stdout.decode().split("\n")[1].strip()
    return None


run_configurators_mapping: Dict[ConfigurationType, Type[BaseRunConfigurator]] = {
    cls.TYPE: cls
    for cls in [
        TaskRunConfigurator,
        DevEnvironmentRunConfigurator,
        ServiceRunConfigurator,
    ]
}
