import argparse
import os
import subprocess
from typing import Dict, List, Optional, Type

import dstack._internal.core.models.resources as resources
from dstack._internal.cli.services.args import disk_spec, env_var, gpu_spec, port_mapping
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.common import is_core_model_instance
from dstack._internal.core.models.configurations import (
    BaseConfiguration,
    BaseConfigurationWithPorts,
    DevEnvironmentConfiguration,
    EnvSentinel,
    PortMapping,
    RunConfigurationType,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.utils.interpolator import VariablesInterpolator


class BaseRunConfigurator:
    TYPE: RunConfigurationType = None

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
        parser.add_argument(
            "--gpu",
            type=gpu_spec,
            help="Request GPU for the run. "
            "The format is [code]NAME[/]:[code]COUNT[/]:[code]MEMORY[/] (all parts are optional)",
            dest="gpu_spec",
            metavar="SPEC",
        )
        parser.add_argument(
            "--disk",
            type=disk_spec,
            help="Request the size range of disk for the run. Example [code]--disk 100GB..[/].",
            metavar="RANGE",
            dest="disk_spec",
        )

    @classmethod
    def apply(cls, args: argparse.Namespace, unknown: List[str], conf: BaseConfiguration):
        if args.envs:
            for k, v in args.envs:
                conf.env[k] = v
        if args.gpu_spec:
            gpu = (conf.resources.gpu or resources.GPUSpec()).dict()
            gpu.update(args.gpu_spec)
            conf.resources.gpu = resources.GPUSpec.parse_obj(gpu)
        if args.disk_spec:
            conf.resources.disk = args.disk_spec

        for k, v in conf.env.items():
            if is_core_model_instance(v, EnvSentinel):
                try:
                    conf.env[k] = v.from_env(os.environ)
                except ValueError as e:
                    raise ConfigurationError(*e.args)

        cls.interpolate_run_args(conf.setup, unknown)

    @classmethod
    def interpolate_run_args(cls, value: List[str], unknown):
        run_args = " ".join(unknown)
        interpolator = VariablesInterpolator({"run": {"args": run_args}}, skip=["secrets"])
        for i in range(len(value)):
            value[i] = interpolator.interpolate(value[i])


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
    def apply(cls, args: argparse.Namespace, unknown: List[str], conf: BaseConfigurationWithPorts):
        super().apply(args, unknown, conf)
        if args.ports:
            conf.ports = list(merge_ports(conf.ports, args.ports).values())


class TaskRunConfigurator(RunWithPortsConfigurator):
    TYPE = RunConfigurationType.TASK

    @classmethod
    def apply(cls, args: argparse.Namespace, unknown: List[str], conf: TaskConfiguration):
        super().apply(args, unknown, conf)

        cls.interpolate_run_args(conf.commands, unknown)


class DevEnvironmentRunConfigurator(RunWithPortsConfigurator):
    TYPE = RunConfigurationType.DEV_ENVIRONMENT

    @classmethod
    def apply(
        cls, args: argparse.Namespace, unknown: List[str], conf: DevEnvironmentConfiguration
    ):
        super().apply(args, unknown, conf)
        if conf.ide == "vscode" and conf.version is None:
            conf.version = _detect_vscode_version()
            if conf.version is None:
                console.print(
                    "[secondary]Unable to detect the VS Code version and pre-install extensions. "
                    "Fix by opening [code]Command Palette[/code], executing [code]Shell Command: "
                    "Install 'code' command in PATH[/code], and restarting terminal.[/]\n"
                )


class ServiceRunConfigurator(BaseRunConfigurator):
    TYPE = RunConfigurationType.SERVICE

    @classmethod
    def apply(cls, args: argparse.Namespace, unknown: List[str], conf: ServiceConfiguration):
        super().apply(args, unknown, conf)

        cls.interpolate_run_args(conf.commands, unknown)


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


run_configurators_mapping: Dict[RunConfigurationType, Type[BaseRunConfigurator]] = {
    cls.TYPE: cls
    for cls in [
        TaskRunConfigurator,
        DevEnvironmentRunConfigurator,
        ServiceRunConfigurator,
    ]
}
