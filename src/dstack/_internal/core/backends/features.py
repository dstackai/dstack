from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    ComputeWithGatewaySupport,
    ComputeWithGroupProvisioningSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithMultinodeSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithPrivateGatewaySupport,
    ComputeWithPrivilegedSupport,
    ComputeWithReservationSupport,
    ComputeWithResourceListingSupport,
    ComputeWithVolumeSupport,
)
from dstack._internal.core.backends.base.configurator import Configurator
from dstack._internal.core.backends.configurators import (
    list_builtin_and_registered_configurator_classes,
    list_builtin_configurator_classes,
)
from dstack._internal.core.models.backends.base import BackendType

# The `BACKENDS_WITH_*` lists are computed from built-in configurators. They are checked against
# base backend types (offers, volume and gateway configurations), which are always built-in:
# extensions currently only register wrapper backends such as `dstack`, which callers that check
# project backend types special-case or handle with `get_*()` functions below.
# TODO: Compute the lists from built-in and registered configurators and mark wrapper backends
# if extensions ever need to register base backends.
_configurator_classes = list_builtin_configurator_classes()


def _get_backends_with_compute_feature(
    configurator_classes: list[type[Configurator]],
    compute_feature_class: type,
) -> list[BackendType]:
    backend_types_and_computes = [
        (configurator_class.TYPE, configurator_class.BACKEND_CLASS.COMPUTE_CLASS)
        for configurator_class in configurator_classes
    ]
    backend_types = []
    for backend_type, compute_class in backend_types_and_computes:
        if issubclass(compute_class, compute_feature_class):
            backend_types.append(backend_type)
    return backend_types


# The following backend lists do not include unavailable backends (i.e. backends missing deps).
BACKENDS_WITH_CREATE_INSTANCE_SUPPORT = _get_backends_with_compute_feature(
    configurator_classes=_configurator_classes,
    compute_feature_class=ComputeWithCreateInstanceSupport,
)
BACKENDS_WITH_GROUP_PROVISIONING_SUPPORT = _get_backends_with_compute_feature(
    configurator_classes=_configurator_classes,
    compute_feature_class=ComputeWithGroupProvisioningSupport,
)
BACKENDS_WITH_PRIVILEGED_SUPPORT = _get_backends_with_compute_feature(
    configurator_classes=_configurator_classes,
    compute_feature_class=ComputeWithPrivilegedSupport,
)
BACKENDS_WITH_INSTANCE_VOLUMES_SUPPORT = _get_backends_with_compute_feature(
    configurator_classes=_configurator_classes,
    compute_feature_class=ComputeWithInstanceVolumesSupport,
)
BACKENDS_WITH_MULTINODE_SUPPORT = [BackendType.REMOTE] + _get_backends_with_compute_feature(
    configurator_classes=_configurator_classes,
    compute_feature_class=ComputeWithMultinodeSupport,
)
BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT = _get_backends_with_compute_feature(
    configurator_classes=_configurator_classes,
    compute_feature_class=ComputeWithPlacementGroupSupport,
)
BACKENDS_WITH_RESERVATION_SUPPORT = _get_backends_with_compute_feature(
    configurator_classes=_configurator_classes,
    compute_feature_class=ComputeWithReservationSupport,
)
BACKENDS_WITH_GATEWAY_SUPPORT = _get_backends_with_compute_feature(
    configurator_classes=_configurator_classes,
    compute_feature_class=ComputeWithGatewaySupport,
)
BACKENDS_WITH_PRIVATE_GATEWAY_SUPPORT = _get_backends_with_compute_feature(
    configurator_classes=_configurator_classes,
    compute_feature_class=ComputeWithPrivateGatewaySupport,
)
BACKENDS_WITH_VOLUMES_SUPPORT = _get_backends_with_compute_feature(
    configurator_classes=_configurator_classes,
    compute_feature_class=ComputeWithVolumeSupport,
)


def get_backends_with_resource_listing_support() -> list[BackendType]:
    """
    Unlike the `BACKENDS_WITH_*` lists, includes backends added with `register_configurator()`.
    Orphan cleanup checks project backend types, so wrapper backends such as `dstack`
    must be included if they support resource listing.
    """
    backend_types = []
    for configurator_class in list_builtin_and_registered_configurator_classes():
        # Registered configurators may not declare the classes for introspection
        backend_class = getattr(configurator_class, "BACKEND_CLASS", None)
        compute_class = getattr(backend_class, "COMPUTE_CLASS", None)
        if compute_class is not None and issubclass(
            compute_class, ComputeWithResourceListingSupport
        ):
            backend_types.append(configurator_class.TYPE)
    return backend_types
