from dstack._internal.core.models.fleets import FleetSpec
from dstack._internal.core.models.gateways import GatewaySpec
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.core.models.volumes import VolumeSpec
from dstack.plugins._models import ApplySpec


class ApplyPolicy:
    """
    A base apply policy class to modify specs on `dstack apply`.
    Subclass it and return the subclass instance in `Plugin.get_apply_policies()`.
    """

    def on_apply(self, user: str, project: str, spec: ApplySpec) -> ApplySpec:
        """
        Modify `spec` before it's applied.
        Raise `ValueError` for `spec` to be rejected as invalid.

        This method can be called twice:
          * first when a user gets a plan
          * second when a user applies a plan

        In both cases, the original spec is passed, so the method does not
        need to check if it modified the spec before.

        It's safe to modify and return `spec` without copying.
        """
        if isinstance(spec, RunSpec):
            return self.on_run_apply(user=user, project=project, spec=spec)
        if isinstance(spec, FleetSpec):
            return self.on_fleet_apply(user=user, project=project, spec=spec)
        if isinstance(spec, VolumeSpec):
            return self.on_volume_apply(user=user, project=project, spec=spec)
        if isinstance(spec, GatewaySpec):
            return self.on_gateway_apply(user=user, project=project, spec=spec)
        raise ValueError(f"Unknown spec type {type(spec)}")

    def on_run_apply(self, user: str, project: str, spec: RunSpec) -> RunSpec:
        """
        Called by the default `on_apply()` implementation for runs.
        """
        return spec

    def on_fleet_apply(self, user: str, project: str, spec: FleetSpec) -> FleetSpec:
        """
        Called by the default `on_apply()` implementation for fleets.
        """
        return spec

    def on_volume_apply(self, user: str, project: str, spec: VolumeSpec) -> VolumeSpec:
        """
        Called by the default `on_apply()` implementation for volumes.
        """
        return spec

    def on_gateway_apply(self, user: str, project: str, spec: GatewaySpec) -> GatewaySpec:
        """
        Called by the default `on_apply()` implementation for gateways.
        """
        return spec


class Plugin:
    """
    A base plugin class.
    Plugins must subclass it, implement public methods,
    and register the subclass as an entrypoint of the package
    (https://packaging.python.org/en/latest/specifications/entry-points/).
    """

    def get_apply_policies(self) -> list[ApplyPolicy]:
        return []
