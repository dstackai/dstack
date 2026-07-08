import contextlib
import threading
import time
from collections import defaultdict
from typing import Optional

from dstack._internal.core.backends.base.offers import gpu_matches_gpu_spec
from dstack._internal.core.backends.slurm.client import SlurmClient
from dstack._internal.core.backends.slurm.models import (
    SlurmBackendConfigWithCreds,
    SlurmClusterConfigWithCreds,
)
from dstack._internal.core.backends.slurm.resources import GPUModel, Node
from dstack._internal.core.models.resources import GPUSpec


class SlurmCluster:
    NODES_CACHE_TTL = 600
    PARTITIONS_CACHE_TTL = 600

    def __init__(self, config: SlurmClusterConfigWithCreds) -> None:
        self.region = self.name = config.name
        self.hostname = config.hostname
        self.port = config.port or 22
        self.user = config.user

        self._private_key = config.private_key.content
        self._cpu_partitions = config.cpu_partitions

        gpu_model_to_partitions_map: defaultdict[GPUModel, set[str]] = defaultdict(set)
        for gpu_partition_config in config.gpu_partitions or []:
            gpu_model = GPUModel.from_string(gpu_partition_config.gpu)
            for partition in gpu_partition_config.partitions:
                gpu_model_to_partitions_map[gpu_model].add(partition)
        self._gpu_model_to_partitions_map = dict(gpu_model_to_partitions_map)

        partition_to_gpu_model_map: dict[str, GPUModel] = {}
        for gpu_model, partitions in self._gpu_model_to_partitions_map.items():
            for partition in partitions:
                other_gpu_model = partition_to_gpu_model_map.get(partition)
                if other_gpu_model is not None:
                    raise ValueError(
                        f"Multiple GPU models mapped in cluster {self.name!r}"
                        f" partition {partition!r}: {other_gpu_model}, {gpu_model}"
                    )
                partition_to_gpu_model_map[partition] = gpu_model
        self._partition_to_gpu_model_map = partition_to_gpu_model_map

        now = time.monotonic()
        self._nodes_cache: tuple[Node, ...] = ()
        self._nodes_cache_lock = threading.Lock()
        self._nodes_cache_expiry = now
        self._partitions_cache: list[str] = []
        self._partitions_cache_lock = threading.Lock()
        self._partitions_cache_expiry = now

    def __str__(self) -> str:
        return f"(name={self.name} hostname={self.hostname})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}{self}"

    def get_client(self, *, timeout: Optional[float] = None) -> SlurmClient:
        return SlurmClient(
            hostname=self.hostname,
            port=self.port,
            user=self.user,
            private_key=self._private_key,
            timeout=timeout,
        )

    def get_cpu_partitions(self) -> Optional[set[str]]:
        """
        Returns all configured CPU partitions. The result should be filtered against partitions
        actually present in the cluster, see `get_discovered_partitions()`.

        If `cpu_partitions` is not set in the config, `None` is returned.
        if `cpu_partitions` is set to an empty array, an empty set is returned.
        """
        if self._cpu_partitions is None:
            return None
        return set(self._cpu_partitions)

    def get_gpu_partitions(self) -> set[str]:
        """
        Returns all configured GPU partitions. The result should be filtered against partitions
        actually present in the cluster, see `get_discovered_partitions()`.

        If `gpu_partitions` is not set or set to an empty array in the config, an empty set
        is returned.
        """
        return set(self._partition_to_gpu_model_map.keys())

    def filter_gpu_partitions(self, gpu_spec: GPUSpec) -> set[str]:
        """
        Filter configured GPU partitions by GPUSpec. The result should be filtered against
        partitions actually present in the cluster, see `get_discovered_partitions()`.
        """
        filtered_partitions: set[str] = set()
        for gpu_model, partitions in self._gpu_model_to_partitions_map.items():
            if gpu_matches_gpu_spec(gpu_model.to_gpu(), gpu_spec):
                filtered_partitions.update(partitions)
        return filtered_partitions

    def get_partition_gpu_model(self, partition: str) -> Optional[GPUModel]:
        """
        Returns a GPU configured for the given partition, if any.
        """
        return self._partition_to_gpu_model_map.get(partition)

    def get_discovered_nodes(self, client: Optional[SlurmClient] = None) -> tuple[Node, ...]:
        """
        Returns all nodes discovered in the cluster. The result is cached.
        """
        with self._nodes_cache_lock:
            now = time.monotonic()
            if now >= self._nodes_cache_expiry:
                self._nodes_cache = tuple(self._discover_nodes(client))
                self._nodes_cache_expiry = now + self.NODES_CACHE_TTL
            return self._nodes_cache

    def get_discovered_partitions(self, client: Optional[SlurmClient] = None) -> set[str]:
        """
        Returns all partitions discovered in the cluster. The result is cached.
        """
        with self._partitions_cache_lock:
            now = time.monotonic()
            if now >= self._partitions_cache_expiry:
                self._partitions_cache = self._discover_partitions(client)
                self._partitions_cache_expiry = now + self.PARTITIONS_CACHE_TTL
            return set(self._partitions_cache)

    def _discover_nodes(self, client: Optional[SlurmClient]) -> list[Node]:
        with self._get_client_context(client) as client:
            client.connect()
            return client.get_nodes()

    def _discover_partitions(self, client: Optional[SlurmClient]) -> list[str]:
        with self._get_client_context(client) as client:
            client.connect()
            return client.get_partitions()

    def _get_client_context(
        self, client: Optional[SlurmClient]
    ) -> contextlib.AbstractContextManager[SlurmClient]:
        if client is None:
            client = self.get_client()
            return contextlib.closing(client)
        return contextlib.nullcontext(client)


def get_clusters_from_backend_config(config: SlurmBackendConfigWithCreds) -> list[SlurmCluster]:
    return [SlurmCluster(c) for c in config.clusters]
