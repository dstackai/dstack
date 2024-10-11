from datetime import datetime
from typing import Any, List

from dstack._internal.core.models.common import CoreModel


class Metric(CoreModel):
    name: str
    timestamps: List[datetime]
    values: List[Any]


class JobMetrics(CoreModel):
    metrics: List[Metric]
