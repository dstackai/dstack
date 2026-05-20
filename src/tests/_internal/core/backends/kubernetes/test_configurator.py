from unittest.mock import Mock

import pytest

from dstack._internal.core.backends.kubernetes.configurator import KubernetesConfigurator
from dstack._internal.core.backends.kubernetes.models import (
    KubeconfigConfig,
    KubernetesBackendConfigWithCreds,
    KubernetesContextConfig,
    KubernetesProxyJumpConfig,
)
from dstack._internal.core.errors import ServerClientError


@pytest.fixture
def get_clusters_mock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock(return_value=[])
    monkeypatch.setattr(
        "dstack._internal.core.backends.kubernetes.configurator.get_clusters_from_backend_config",
        mock,
    )
    return mock


class TestKubernetesConfigurator:
    @pytest.mark.usefixtures("get_clusters_mock")
    def test_validate_config_valid_current_context(self):
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked", filename="-"),
            proxy_jump=KubernetesProxyJumpConfig(hostname=None, port=30022),
            namespace="ns",
        )
        KubernetesConfigurator().validate_config(config, default_creds_enabled=True)

    @pytest.mark.usefixtures("get_clusters_mock")
    def test_validate_config_valid_explicit_contexts(self):
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked", filename="-"),
            contexts=["ctx"],
        )
        KubernetesConfigurator().validate_config(config, default_creds_enabled=True)

    @pytest.mark.usefixtures("get_clusters_mock")
    def test_validate_config_contexts_proxy_jump_mutually_exclusive(self):
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked", filename="-"),
            proxy_jump=KubernetesProxyJumpConfig(hostname=None, port=30022),
            contexts=["ctx"],
        )
        with pytest.raises(ServerClientError, match="proxy_jump must not be set"):
            KubernetesConfigurator().validate_config(config, default_creds_enabled=True)

    @pytest.mark.usefixtures("get_clusters_mock")
    def test_validate_config_contexts_namespace_mutually_exclusive(self):
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked", filename="-"),
            namespace="ns",
            contexts=["ctx"],
        )
        with pytest.raises(ServerClientError, match="namespace must not be set"):
            KubernetesConfigurator().validate_config(config, default_creds_enabled=True)

    @pytest.mark.usefixtures("get_clusters_mock")
    def test_validate_config_duplicate_contexts(self):
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked", filename="-"),
            contexts=[
                "ctx-3",
                KubernetesContextConfig(name="ctx-4"),
                "ctx-1",
                KubernetesContextConfig(name="ctx-1"),
                "ctx-2",
                KubernetesContextConfig(name="ctx-3"),
            ],
        )
        with pytest.raises(ServerClientError, match="duplicate contexts: ctx-1, ctx-3"):
            KubernetesConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_cluster_check_failed(
        self, monkeypatch: pytest.MonkeyPatch, get_clusters_mock: Mock
    ):
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked", filename="-"),
            contexts=["ctx"],
        )

        monkeypatch.setattr(
            "dstack._internal.core.backends.kubernetes.configurator.check_cluster",
            Mock(return_value=False),
        )
        cluster_mock = Mock()
        get_clusters_mock.return_value = [cluster_mock]
        with pytest.raises(ServerClientError, match="Failed to validate cluster") as exc_info:
            KubernetesConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["kubeconfig"]]
