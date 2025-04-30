from dstack.api import Service
from dstack.plugins import ApplyPolicy, GatewaySpec, Plugin, RunSpec, get_plugin_logger

logger = get_plugin_logger(__name__)


class ExamplePolicy(ApplyPolicy):
    def on_run_apply(self, user: str, project: str, spec: RunSpec) -> RunSpec:
        # Forcing some limits
        spec.configuration.max_price = 2.0
        spec.configuration.max_duration = "1d"
        # Setting some extra tags
        if spec.configuration.tags is None:
            spec.configuration.tags = {}
        spec.configuration.tags |= {
            "team": "my_team",
        }
        # Forbid something
        if spec.configuration.privileged:
            logger.warning("User %s tries to run privileged containers", user)
            raise ValueError("Running privileged containers is forbidden")
        # Set some service-specific properties
        if isinstance(spec.configuration, Service):
            spec.configuration.https = True
        return spec

    def on_gateway_apply(self, user: str, project: str, spec: GatewaySpec) -> GatewaySpec:
        # Forbid creating new gateways altogether
        raise ValueError("Creating gateways is forbidden")


class ExamplePlugin(Plugin):
    def get_apply_policies(self) -> list[ApplyPolicy]:
        return [ExamplePolicy()]
