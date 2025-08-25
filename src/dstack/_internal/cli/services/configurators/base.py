import argparse
import os
from abc import ABC, abstractmethod
from typing import Generic, List, TypeVar, Union, cast

from dstack._internal.cli.services.args import env_var
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import (
    AnyApplyConfiguration,
    ApplyConfigurationType,
)
from dstack._internal.core.models.envs import Env, EnvSentinel, EnvVarTuple
from dstack.api._public import Client

ArgsParser = Union[argparse._ArgumentGroup, argparse.ArgumentParser]

ApplyConfigurationT = TypeVar("ApplyConfigurationT", bound=AnyApplyConfiguration)


class BaseApplyConfigurator(ABC, Generic[ApplyConfigurationT]):
    TYPE: ApplyConfigurationType

    def __init__(self, api_client: Client):
        self.api = api_client

    @abstractmethod
    def apply_configuration(
        self,
        conf: ApplyConfigurationT,
        configuration_path: str,
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
        unknown_args: List[str],
    ):
        """
        Implements `dstack apply` for a given configuration type.

        Args:
            conf: The apply configuration.
            configuration_path: The path to the configuration file.
            command_args: The args parsed by `dstack apply`.
            configurator_args: The known args parsed by `cls.get_parser()`.
            unknown_args: The unknown args after parsing by `cls.get_parser()`.
        """
        pass

    @abstractmethod
    def delete_configuration(
        self,
        conf: ApplyConfigurationT,
        configuration_path: str,
        command_args: argparse.Namespace,
    ):
        """
        Implements `dstack delete` for a given configuration type.

        Args:
            conf: The apply configuration.
            configuration_path: The path to the configuration file.
            command_args: The args parsed by `dstack delete`.
        """
        pass

    @classmethod
    def get_parser(cls) -> argparse.ArgumentParser:
        """
        Returns a parser to parse configuration-specific args.
        """
        parser = argparse.ArgumentParser()
        cls.register_args(parser)
        return parser

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        """
        Adds configuration-specific args to `parser`.
        This is separated from `cls.get_parser()` so that `dstack apply` can register
        args with different parser to show unified help.
        """
        pass


class ApplyEnvVarsConfiguratorMixin:
    @classmethod
    def register_env_args(cls, parser: ArgsParser):
        parser.add_argument(
            "-e",
            "--env",
            type=env_var,
            action="append",
            help="Environment variables",
            dest="env_vars",
            default=[],
            metavar="KEY[=VALUE]",
        )

    def apply_env_vars(self, env: Env, configurator_args: argparse.Namespace) -> None:
        for k, v in cast(List[EnvVarTuple], configurator_args.env_vars):
            env[k] = v
        for k, v in env.items():
            if isinstance(v, EnvSentinel):
                try:
                    env[k] = v.from_env(os.environ)
                except ValueError as e:
                    raise ConfigurationError(*e.args)
