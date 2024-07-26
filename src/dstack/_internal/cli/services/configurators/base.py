import argparse
from abc import ABC, abstractmethod
from typing import List

from dstack._internal.core.models.configurations import (
    AnyApplyConfiguration,
    ApplyConfigurationType,
)
from dstack.api._public import Client


class BaseApplyConfigurator(ABC):
    TYPE: ApplyConfigurationType

    def __init__(self, api_client: Client):
        self.api = api_client

    @abstractmethod
    def apply_configuration(
        self,
        conf: AnyApplyConfiguration,
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
            unknown_args: The unknown args after parsing by `cls.get_parser()`
        """
        pass

    @abstractmethod
    def delete_configuration(
        self,
        conf: AnyApplyConfiguration,
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
