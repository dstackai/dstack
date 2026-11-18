from typing import Optional

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.kubernetes.backend import KubernetesBackend
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesBackendConfig,
    KubernetesBackendConfigWithCreds,
    KubernetesConfig,
    KubernetesProxyJumpConfig,
    KubernetesStoredConfig,
)
from dstack._internal.core.backends.kubernetes.resources import (
    parse_node_selector_requirement,
    parse_quantity,
    parse_toleration,
    validate_quantity,
)
from dstack._internal.core.backends.kubernetes.utils import (
    check_cluster,
    get_clusters_from_backend_config,
)
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import validate_extra_ignore, validate_json_extra_ignore
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# Sanity floors that catch unit mistakes, e.g., `memory: 512` (bytes). Measured with the jump pod
# image: below 100m, SSH handshakes through the jump pod slow down sharply (~0.5s at 50m, ~2s at
# 10m); 32Mi fits the container (~9Mi) and a few sessions (~1.6Mi each).
_JUMP_POD_MIN_CPU = "100m"
_JUMP_POD_MIN_MEMORY = "32Mi"


class KubernetesConfigurator(
    Configurator[
        KubernetesBackendConfig,
        KubernetesBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.KUBERNETES
    BACKEND_CLASS = KubernetesBackend

    def validate_config(
        self, config: KubernetesBackendConfigWithCreds, default_creds_enabled: bool
    ):
        self._check_config_contexts(config)
        self._check_config_proxy_jumps(config)
        try:
            clusters = get_clusters_from_backend_config(config, request_timeout=10, retries=0)
        except Exception as e:
            raise ServerClientError(str(e))
        for cluster in clusters:
            if not check_cluster(cluster):
                raise_invalid_credentials_error(
                    fields=[["kubeconfig"]],
                    details=f"Failed to validate cluster {cluster}",
                )

    def create_backend(
        self, project_name: str, config: KubernetesBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=validate_extra_ignore(KubernetesStoredConfig, config).model_dump_json(),
            auth="",
        )

    def get_backend_config_with_creds(
        self, record: BackendRecord
    ) -> KubernetesBackendConfigWithCreds:
        config = self._get_config(record)
        return validate_extra_ignore(KubernetesBackendConfigWithCreds, config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> KubernetesBackendConfig:
        config = self._get_config(record)
        return validate_extra_ignore(KubernetesBackendConfig, config)

    def get_backend(self, record: BackendRecord) -> KubernetesBackend:
        return KubernetesBackend(self._get_config(record))

    def _get_config(self, record: BackendRecord) -> KubernetesConfig:
        return validate_json_extra_ignore(KubernetesConfig, record.config)

    def _check_config_contexts(self, config: KubernetesBackendConfig):
        if config.contexts is None:
            return
        if config.proxy_jump is not None:
            raise ServerClientError("proxy_jump must not be set if contexts is set")
        if config.namespace is not None:
            raise ServerClientError("namespace must not be set if contexts is set")
        seen: set[str] = set()
        duplicates: set[str] = set()
        for context in config.contexts:
            if isinstance(context, str):
                name = context
            else:
                name = context.name
            if name in seen:
                duplicates.add(name)
            else:
                seen.add(name)
        if duplicates:
            raise ServerClientError(f"duplicate contexts: {', '.join(sorted(duplicates))}")

    def _check_config_proxy_jumps(self, config: KubernetesBackendConfig):
        if config.proxy_jump is not None:
            self._check_proxy_jump(config.proxy_jump)
        for context in config.contexts or []:
            if not isinstance(context, str) and context.proxy_jump is not None:
                self._check_proxy_jump(context.proxy_jump, context_name=context.name)

    def _check_proxy_jump(
        self, proxy_jump: KubernetesProxyJumpConfig, *, context_name: Optional[str] = None
    ):
        in_context = f" in context {context_name!r}" if context_name is not None else ""
        for field, quantity, min_quantity in [
            ("cpu", proxy_jump.cpu, _JUMP_POD_MIN_CPU),
            ("memory", proxy_jump.memory, _JUMP_POD_MIN_MEMORY),
        ]:
            if quantity is None:
                continue
            try:
                validate_quantity(quantity)
            except ValueError:
                reason = "must be a Kubernetes quantity"
            else:
                if parse_quantity(quantity) >= parse_quantity(min_quantity):
                    continue
                reason = f"must be at least {min_quantity}"
            raise ServerClientError(
                f"invalid proxy_jump.{field} value {quantity!r}{in_context}: {reason}"
            )
        for field, items, parse in [
            ("node_selector", proxy_jump.node_selector, parse_node_selector_requirement),
            ("tolerations", proxy_jump.tolerations, parse_toleration),
        ]:
            for item in items or []:
                try:
                    parse(item)
                except ValueError as e:
                    raise ServerClientError(
                        f"invalid proxy_jump.{field} item {item!r}{in_context}: {e}"
                    )
