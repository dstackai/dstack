import datetime
import math
from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel

import dstack._internal.utils.common as common_utils
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.proxy.gateway.schemas.stats import PerWindowStats


class ReplicaInfo(BaseModel):
    """
    Attributes:
        active (bool): starting/running/retrying or downscaled
        timestamp (datetime.datetime): `submitted_at` for active, `last_processed_at` for inactive
    """

    active: bool
    timestamp: datetime.datetime


class BaseServiceScaler(ABC):
    @abstractmethod
    def scale(self, replicas: List[ReplicaInfo], stats: Optional[PerWindowStats]) -> int:
        """
        Args:
            replicas: list of all replicas
            stats: service usage stats

        Returns:
            diff: number of replicas to add or remove
        """
        pass


class ManualScaler(BaseServiceScaler):
    """
    Scales replicas to keep it between `min_replicas` and `max_replicas`
    in case `min_replicas` or `max_replicas` change.
    """

    def __init__(
        self,
        min_replicas: int,
        max_replicas: int,
    ):
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas

    def scale(self, replicas: List[ReplicaInfo], stats: Optional[PerWindowStats]) -> int:
        active_replicas = [r for r in replicas if r.active]
        target_replicas = len(active_replicas)
        # clip the target replicas to the min and max values
        target_replicas = min(max(target_replicas, self.min_replicas), self.max_replicas)
        return target_replicas - len(active_replicas)


class RPSAutoscaler(BaseServiceScaler):
    def __init__(
        self,
        min_replicas: int,
        max_replicas: int,
        target: float,
        scale_up_delay: int,
        scale_down_delay: int,
    ):
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        self.target = target
        self.scale_up_delay = scale_up_delay
        self.scale_down_delay = scale_down_delay

    def scale(self, replicas: List[ReplicaInfo], stats: Optional[PerWindowStats]) -> int:
        if not stats:
            return 0

        now = common_utils.get_current_datetime()
        active_replicas = [r for r in replicas if r.active]
        last_scaled_at = max((r.timestamp for r in replicas), default=None)

        # calculate the average RPS over the last minute
        rps = stats[60].requests / 60
        target_replicas = math.ceil(rps / self.target)
        # clip the target replicas to the min and max values
        target_replicas = min(max(target_replicas, self.min_replicas), self.max_replicas)

        if target_replicas > len(active_replicas):
            if len(active_replicas) == 0:
                # no replicas, scale up immediately
                return target_replicas
            if (
                last_scaled_at is not None
                and (now - last_scaled_at).total_seconds() < self.scale_up_delay
            ):
                # too early to scale up, wait for the delay
                return 0
            return target_replicas - len(active_replicas)
        elif target_replicas < len(active_replicas):
            if (
                last_scaled_at is not None
                and (now - last_scaled_at).total_seconds() < self.scale_down_delay
            ):
                # too early to scale down, wait for the delay
                return 0
            return target_replicas - len(active_replicas)
        return 0


def get_service_scaler(conf: ServiceConfiguration) -> BaseServiceScaler:
    if conf.scaling is None:
        return ManualScaler(
            min_replicas=conf.replicas.min,
            max_replicas=conf.replicas.max,
        )
    if conf.scaling.metric == "rps":
        return RPSAutoscaler(
            # replicas count validated by configuration model
            min_replicas=conf.replicas.min,
            max_replicas=conf.replicas.max,
            target=conf.scaling.target,
            scale_up_delay=conf.scaling.scale_up_delay,
            scale_down_delay=conf.scaling.scale_down_delay,
        )
    raise ValueError(f"No scaler found for scaling parameters {conf.scaling}")
