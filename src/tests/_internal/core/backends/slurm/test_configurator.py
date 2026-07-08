from dstack._internal.core.backends.base.configurator import BackendRecord
from dstack._internal.core.backends.slurm.configurator import SlurmConfigurator
from dstack._internal.core.backends.slurm.models import (
    SlurmBackendConfigWithCreds,
    SlurmClusterConfig,
    SlurmClusterConfigWithCreds,
)

PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nSECRET\n-----END OPENSSH PRIVATE KEY-----"


HOSTNAME = "login.secret.example"
PORT = 2222
USER = "alice"


def _make_backend_record() -> BackendRecord:
    config = SlurmBackendConfigWithCreds(
        clusters=[
            {
                "name": "c1",
                "hostname": HOSTNAME,
                "port": PORT,
                "user": USER,
                "private_key": {"content": PRIVATE_KEY},
            }
        ]
    )
    return SlurmConfigurator().create_backend("proj", config)


class TestSlurmConfiguratorCreds:
    def test_without_creds_strips_sensitive_fields(self):
        record = _make_backend_record()
        config = SlurmConfigurator().get_backend_config_without_creds(record)
        cluster = config.clusters[0]
        # The credentialless cluster config exposes only non-sensitive fields; connection
        # details and the private key must not be present at all.
        assert set(cluster.__fields__) == {"name", "gpu_partitions", "cpu_partitions"}
        rendered = config.json()
        for secret in (PRIVATE_KEY, HOSTNAME, str(PORT), USER):
            assert secret not in rendered

    def test_with_creds_keeps_sensitive_fields(self):
        record = _make_backend_record()
        cluster = SlurmConfigurator().get_backend_config_with_creds(record).clusters[0]
        assert cluster.private_key.content == PRIVATE_KEY
        assert cluster.hostname == HOSTNAME
        assert cluster.port == PORT
        assert cluster.user == USER

    def test_with_and_without_cluster_configs_are_not_subclasses(self):
        # A subclass relationship would let a `list[SlurmClusterConfig]` field accept a
        # creds-bearing instance as-is and leak the private key into without-creds responses.
        assert not issubclass(SlurmClusterConfigWithCreds, SlurmClusterConfig)
        assert not issubclass(SlurmClusterConfig, SlurmClusterConfigWithCreds)
