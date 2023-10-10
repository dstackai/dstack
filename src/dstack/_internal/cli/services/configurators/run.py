import argparse
import re
from typing import Dict, List, Tuple, Type

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import (
    BaseConfiguration,
    BaseConfigurationWithPorts,
    ConfigurationType,
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


run_configurators_mapping: Dict[ConfigurationType, Type[BaseRunConfigurator]] = {
    cls.TYPE: cls
    for cls in [
        TaskRunConfigurator,
        DevEnvironmentRunConfigurator,
        ServiceRunConfigurator,
    ]
}
