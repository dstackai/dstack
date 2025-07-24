from dstack._internal.core.models.runs import Probe
from dstack._internal.server.models import ProbeModel


def probe_model_to_probe(probe_model: ProbeModel) -> Probe:
    return Probe(success_streak=probe_model.success_streak)
