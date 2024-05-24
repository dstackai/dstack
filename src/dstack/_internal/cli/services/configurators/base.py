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
        self.api_client = api_client

    @abstractmethod
    def apply_configuration(self, conf: AnyApplyConfiguration, args: argparse.Namespace):
        pass

    @abstractmethod
    def delete_configuration(self, conf: AnyApplyConfiguration, args: argparse.Namespace):
        pass

    def register_args(self, parser: argparse.ArgumentParser):
        pass

    def apply_args(
        self, args: argparse.Namespace, unknown: List[str], conf: AnyApplyConfiguration
    ):
        pass
