from dstack._internal.core.models.gateways import (
    ALBGatewayLoadBalancer,
    AnyGatewayLoadBalancer,
    GatewayConfiguration,
)
from dstack._internal.core.services.diff import ModelDiff, diff_models


def diff_gateway_configurations(old: GatewayConfiguration, new: GatewayConfiguration) -> ModelDiff:
    return diff_models(
        old,
        new,
        # default=None => default should stay unchanged => shouldn't be in the diff
        reset={"default"} if new.default is None else {},
    )


def get_effective_load_balancer(
    configuration: GatewayConfiguration,
) -> AnyGatewayLoadBalancer | None:
    if configuration.load_balancer is not None:
        return configuration.load_balancer
    if configuration.certificate is not None and configuration.certificate.type == "acm":
        return ALBGatewayLoadBalancer()
    return None
