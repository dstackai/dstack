from dstack._internal.core.models.runs import Probe, ProbeSpec
from dstack._internal.server.models import ProbeModel


def probe_model_to_probe(probe_model: ProbeModel) -> Probe:
    return Probe(success_streak=probe_model.success_streak)


def is_probe_ready(probe: ProbeModel, spec: ProbeSpec) -> bool:
    return probe.success_streak >= spec.ready_after
