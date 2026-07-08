import concurrent.futures

from dstack._internal.core.backends.base.configurator import BackendRecord, Configurator
from dstack._internal.core.backends.slurm.backend import SlurmBackend
from dstack._internal.core.backends.slurm.cluster import (
    SlurmCluster,
    get_clusters_from_backend_config,
)
from dstack._internal.core.backends.slurm.models import (
    SlurmBackendConfig,
    SlurmBackendConfigWithCreds,
    SlurmConfig,
    SlurmStoredConfig,
)
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType


class SlurmConfigurator(
    Configurator[
        SlurmBackendConfig,
        SlurmBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.SLURM
    BACKEND_CLASS = SlurmBackend

    def validate_config(self, config: SlurmBackendConfigWithCreds, default_creds_enabled: bool):
        try:
            clusters = get_clusters_from_backend_config(config)
        except Exception as e:
            raise ServerClientError(str(e))
        self._check_clusters(clusters)

    def create_backend(
        self, project_name: str, config: SlurmBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=SlurmStoredConfig.__response__.parse_obj(config).json(),
            auth="",
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> SlurmBackendConfigWithCreds:
        config = self._get_config(record)
        return SlurmBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> SlurmBackendConfig:
        config = self._get_config(record)
        return SlurmBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> SlurmBackend:
        return SlurmBackend(self._get_config(record))

    def _get_config(self, record: BackendRecord) -> SlurmConfig:
        return SlurmConfig.__response__.parse_raw(record.config)

    def _check_clusters(self, clusters: list[SlurmCluster]) -> None:
        error_messages: list[str] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            future_to_cluster_map: dict[concurrent.futures.Future[None], SlurmCluster] = {}
            for cluster in clusters:
                future = executor.submit(self._check_cluster, cluster)
                future_to_cluster_map[future] = cluster
            for future in concurrent.futures.as_completed(future_to_cluster_map):
                exc = future.exception()
                if exc is not None:
                    error_messages.append(f"{future_to_cluster_map[future]}: {exc}")
        if error_messages:
            raise ServerClientError(f"Failed to check clusters: {', '.join(error_messages)}")

    def _check_cluster(self, cluster: SlurmCluster) -> None:
        with cluster.get_client(timeout=10) as client:
            client.ping()
