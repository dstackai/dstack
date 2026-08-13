from dstack._internal.core.models.gateways import GatewayConfiguration
from dstack._internal.core.services.diff import ModelDiff, diff_models


def diff_gateway_configurations(old: GatewayConfiguration, new: GatewayConfiguration) -> ModelDiff:
    return diff_models(
        old,
        new,
        # default=None => default should stay unchanged => shouldn't be in the diff
        reset={"default"} if new.default is None else {},
    )
