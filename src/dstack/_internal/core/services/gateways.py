from dstack._internal.core.models.gateways import (
    ALBGatewayLoadBalancer,
    AnyGatewayCertificate,
    AnyGatewayLoadBalancer,
    GatewayConfiguration,
)
from dstack._internal.core.services.diff import ModelDiff, diff_models

LOAD_BALANCER_TERMINATED_CERTIFICATE_TYPES = ("acm", "gcp-cm")


def diff_gateway_configurations(old: GatewayConfiguration, new: GatewayConfiguration) -> ModelDiff:
    return diff_models(
        old,
        new,
        # default=None => default should stay unchanged => shouldn't be in the diff
        reset={"default"} if new.default is None else {},
    )


def is_tls_terminated_at_load_balancer(
    certificate: AnyGatewayCertificate | None,
) -> bool:
    return (
        certificate is not None and certificate.type in LOAD_BALANCER_TERMINATED_CERTIFICATE_TYPES
    )


def get_effective_load_balancer(
    configuration: GatewayConfiguration,
) -> AnyGatewayLoadBalancer | None:
    if configuration.load_balancer is not None:
        return configuration.load_balancer
    # `acm` implies an ALB for backward compatibility
    if configuration.certificate is not None and configuration.certificate.type == "acm":
        return ALBGatewayLoadBalancer()
    return None
