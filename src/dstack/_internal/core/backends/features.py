from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    ComputeWithGatewaySupport,
    ComputeWithMultinodeSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithPrivateGatewaySupport,
    ComputeWithReservationSupport,
    ComputeWithVolumeSupport,
)
from dstack._internal.core.backends.base.configurator import Configurator
from dstack._internal.core.backends.configurators import list_available_configurator_classes
from dstack._internal.core.backends.local.compute import LocalCompute
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.settings import LOCAL_BACKEND_ENABLED

_configurator_classes = list_available_configurator_classes()


def _get_backends_with_compute_feature(
    configurator_classes: list[type[Configurator]],
    compute_feature_class: type,
) -> list[BackendType]:
    backend_types_and_computes = [
        (configurator_class.TYPE, configurator_class.BACKEND_CLASS.COMPUTE_CLASS)
        for configurator_class in configurator_classes
    ]
    if LOCAL_BACKEND_ENABLED:
        backend_types_and_computes.append((BackendType.LOCAL, LocalCompute))
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
