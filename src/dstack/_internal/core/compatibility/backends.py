from dstack._internal.core.backends.gcp.models import GCPBackendConfigWithCreds
from dstack._internal.core.backends.hotaisle.models import HotAisleBackendConfigWithCreds
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesBackendConfigWithCreds,
    KubernetesProxyJumpConfig,
)
from dstack._internal.core.backends.models import AnyBackendConfigWithCreds
from dstack._internal.core.models.common import IncludeExcludeStrDictType


def get_backend_config_excludes(config: AnyBackendConfigWithCreds) -> IncludeExcludeStrDictType:
    """
    Returns `config` exclude mapping to exclude certain fields from the create/update backend
    request. Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    excludes: IncludeExcludeStrDictType = {}
    if isinstance(config, GCPBackendConfigWithCreds) and config.tpu is None:
        excludes["tpu"] = True
    if isinstance(config, HotAisleBackendConfigWithCreds) and config.bare_metal is None:
        excludes["bare_metal"] = True
    if isinstance(config, KubernetesBackendConfigWithCreds):
        if config.proxy_jump is not None:
            excludes["proxy_jump"] = _get_kubernetes_proxy_jump_excludes([config.proxy_jump])
        if config.contexts is not None:
            proxy_jumps = [
                context.proxy_jump
                for context in config.contexts
                if not isinstance(context, str) and context.proxy_jump is not None
            ]
            excludes["contexts"] = {
                "__all__": {"proxy_jump": _get_kubernetes_proxy_jump_excludes(proxy_jumps)}
            }
    return excludes


def _get_kubernetes_proxy_jump_excludes(
    proxy_jumps: list[KubernetesProxyJumpConfig],
) -> IncludeExcludeStrDictType:
    # A field is excluded only if it's unset in all `proxy_jumps`
    excludes: IncludeExcludeStrDictType = {}
    if all(proxy_jump.cpu is None for proxy_jump in proxy_jumps):
        excludes["cpu"] = True
    if all(proxy_jump.memory is None for proxy_jump in proxy_jumps):
        excludes["memory"] = True
    if all(proxy_jump.node_selector is None for proxy_jump in proxy_jumps):
        excludes["node_selector"] = True
    if all(proxy_jump.tolerations is None for proxy_jump in proxy_jumps):
        excludes["tolerations"] = True
    return excludes
