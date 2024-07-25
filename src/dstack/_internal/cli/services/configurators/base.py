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
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
        unknown_args: List[str],
    ):
        pass

    @abstractmethod
    def delete_configuration(
        self,
        conf: AnyApplyConfiguration,
        command_args: argparse.Namespace,
    ):
        pass

    @classmethod
    def get_parser(cls) -> argparse.ArgumentParser:
        return argparse.ArgumentParser()
