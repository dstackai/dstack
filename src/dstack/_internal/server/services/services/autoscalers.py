import datetime
import math
from abc import ABC, abstractmethod
from typing import Optional

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
    def get_desired_count(
        self,
        current_desired_count: int,
        stats: Optional[PerWindowStats],
        last_scaled_at: Optional[datetime.datetime],
    ) -> int:
        """
        Args:
            stats: service usage stats
            current_desired_count: currently used desired count
            last_scaled_at: last time service was scaled, None if it was never scaled yet

        Returns:
            desired_count: desired count of replicas
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

    def get_desired_count(
        self,
        current_desired_count: int,
        stats: Optional[PerWindowStats],
        last_scaled_at: Optional[datetime.datetime],
    ) -> int:
        # clip the desired count to the min and max values
        return min(max(current_desired_count, self.min_replicas), self.max_replicas)


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

    def get_desired_count(
        self,
        current_desired_count: int,
        stats: Optional[PerWindowStats],
        last_scaled_at: Optional[datetime.datetime],
    ) -> int:
        if not stats:
            return current_desired_count

        now = common_utils.get_current_datetime()

        # calculate the average RPS over the last minute
        rps = stats[60].requests / 60
        new_desired_count = math.ceil(rps / self.target)
        # clip the desired count to the min and max values
        new_desired_count = min(max(new_desired_count, self.min_replicas), self.max_replicas)

        if new_desired_count > current_desired_count:
            if current_desired_count == 0:
                # no replicas, scale up immediately
                return new_desired_count
            if (
                last_scaled_at is not None
                and (now - last_scaled_at).total_seconds() < self.scale_up_delay
            ):
                # too early to scale up, wait for the delay
                return current_desired_count
            return new_desired_count
        elif new_desired_count < current_desired_count:
            if (
                last_scaled_at is not None
                and (now - last_scaled_at).total_seconds() < self.scale_down_delay
            ):
                # too early to scale down, wait for the delay
                return current_desired_count
            return new_desired_count
        return new_desired_count


def get_service_scaler(conf: ServiceConfiguration) -> BaseServiceScaler:
    assert conf.replicas.min is not None
    assert conf.replicas.max is not None
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
