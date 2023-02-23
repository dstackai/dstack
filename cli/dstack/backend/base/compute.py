from abc import ABC, abstractmethod
from typing import Optional, Tuple

from dstack.core.instance import InstanceType
from dstack.core.job import Job, Requirements
from dstack.core.request import RequestHead


class Compute(ABC):
    @abstractmethod
    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        pass

    @abstractmethod
    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        pass

    @abstractmethod
    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        pass

    @abstractmethod
    def terminate_instance(self, request_id: str):
        pass

    @abstractmethod
    def cancel_spot_request(self, request_id: str):
        pass
