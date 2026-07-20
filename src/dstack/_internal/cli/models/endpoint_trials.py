from typing import Optional

from dstack._internal.cli.models.endpoint_presets import EndpointBenchmark
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.resources import ResourcesSpec


class EndpointPresetTrial(CoreModel):
    # TODO: a single task (= single node) for now; revisit multi-task trials
    # (P/D disaggregation) once tasks support node groups.
    task: TaskConfiguration
    resources: ResourcesSpec
    """Exact instance resources the task ran on, as in preset validations."""
    benchmark: Optional[EndpointBenchmark] = None
    """Null only for a failed trial (the configuration never served)."""
