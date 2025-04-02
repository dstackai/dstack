from typing import List, Optional, Type, Union

from dstack._internal.core.backends.base.configurator import Configurator
from dstack._internal.core.models.backends.base import BackendType

_CONFIGURATOR_CLASSES: List[Type[Configurator]] = []


try:
    from dstack._internal.core.backends.aws.configurator import AWSConfigurator

    _CONFIGURATOR_CLASSES.append(AWSConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.azure.configurator import AzureConfigurator

    _CONFIGURATOR_CLASSES.append(AzureConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.cudo.configurator import (
        CudoConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(CudoConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.datacrunch.configurator import (
        DataCrunchConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(DataCrunchConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.gcp.configurator import GCPConfigurator

    _CONFIGURATOR_CLASSES.append(GCPConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.kubernetes.configurator import (
        KubernetesConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(KubernetesConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.lambdalabs.configurator import (
        LambdaConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(LambdaConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.nebius.configurator import (
        NebiusConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(NebiusConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.oci.configurator import OCIConfigurator

    _CONFIGURATOR_CLASSES.append(OCIConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.runpod.configurator import RunpodConfigurator

    _CONFIGURATOR_CLASSES.append(RunpodConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.tensordock.configurator import (
        TensorDockConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(TensorDockConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.vastai.configurator import VastAIConfigurator

    _CONFIGURATOR_CLASSES.append(VastAIConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.core.backends.vultr.configurator import VultrConfigurator

    _CONFIGURATOR_CLASSES.append(VultrConfigurator)
except ImportError:
    pass


_BACKEND_TYPE_TO_CONFIGURATOR_CLASS_MAP = {c.TYPE: c for c in _CONFIGURATOR_CLASSES}
_BACKEND_TYPES = [c.TYPE for c in _CONFIGURATOR_CLASSES]


def get_configurator(backend_type: Union[BackendType, str]) -> Optional[Configurator]:
    """
    Returns an available `Configurator` for a given `backend_type`.
    """
    backend_type = BackendType(backend_type)
    configurator_class = _BACKEND_TYPE_TO_CONFIGURATOR_CLASS_MAP.get(backend_type)
    if configurator_class is None:
        return None
    return configurator_class()


def list_available_backend_types() -> List[BackendType]:
    """
    Lists all backend types available on the server.
    """
    return _BACKEND_TYPES


def list_available_configurator_classes() -> List[type[Configurator]]:
    """
    Lists all backend configurator classes available on the server.
    """
    return _CONFIGURATOR_CLASSES


def register_configurator(configurator: Type[Configurator]):
    """
    A hook to for registering new configurators without importing them.
    Can be used to extend dstack functionality.
    """
    _BACKEND_TYPE_TO_CONFIGURATOR_CLASS_MAP[configurator.TYPE] = configurator
