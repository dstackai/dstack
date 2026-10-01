from dstack._internal.core.backends.hotaisle.models import HotAisleBackendConfigWithCreds
from dstack._internal.core.backends.models import AnyBackendConfigWithCreds
from dstack._internal.core.models.common import IncludeExcludeDictType


def get_backend_config_excludes(config: AnyBackendConfigWithCreds) -> IncludeExcludeDictType:
    """
    Returns `config` exclude mapping to exclude certain fields from the create/update backend
    request. Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    excludes: IncludeExcludeDictType = {}
    if isinstance(config, HotAisleBackendConfigWithCreds) and config.bare_metal is None:
        excludes["bare_metal"] = True
    return excludes
