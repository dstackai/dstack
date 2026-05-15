import logging
from textwrap import dedent
from typing import Optional, Union

import pytest

from dstack._internal.core.backends.kubernetes.models import (
    KubeconfigConfig,
    KubernetesBackendConfigWithCreds,
    KubernetesContextConfig,
    KubernetesProxyJumpConfig,
)
from dstack._internal.core.backends.kubernetes.utils import (
    Cluster,
    get_clusters_from_backend_config,
)


class TestGetClustersFromBackendConfig:
    def make_config(
        self,
        kubeconfig_data: str,
        *,
        contexts: Optional[list[Union[KubernetesContextConfig, str]]] = None,
        namespace: Optional[str] = None,
        proxy_jump: Optional[KubernetesProxyJumpConfig] = None,
    ) -> KubernetesBackendConfigWithCreds:
        return KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data=kubeconfig_data, filename="-"),
            contexts=contexts,
            namespace=namespace,
            proxy_jump=proxy_jump,
        )

    def make_kubeconfig(
        self,
        *,
        current_context: str = "ctx-a",
        # (context name, namespace) pairs
        contexts: tuple[tuple[str, str], ...] = (("ctx-a", "default"),),
    ) -> str:
        clusters_yaml = "\n".join(
            dedent(f"""
                - name: cluster-{name}
                  cluster:
                    server: https://{name}.example.com:6443
            """)
            for name, _ in contexts
        )
        users_yaml = "\n".join(
            dedent(f"""
                - name: user-{name}
                  user:
                    token: token-{name}
                """)
            for name, _ in contexts
        )
        contexts_yaml = "\n".join(
            dedent(f"""
                - name: {name}
                  context:
                    cluster: cluster-{name}
                    user: user-{name}
                    namespace: {namespace}
            """)
            for name, namespace in contexts
        )
        return dedent("""
            apiVersion: v1
            kind: Config
            current-context: {current_context}
            clusters:
            {clusters}
            contexts:
            {contexts}
            users:
            {users}
        """).format(
            current_context=current_context,
            clusters=clusters_yaml,
            contexts=contexts_yaml,
            users=users_yaml,
        )

    def test_returns_single_cluster_using_current_context(self):
        config = self.make_config(
            self.make_kubeconfig(
                current_context="ctx-a",
                contexts=(
                    ("ctx-b", "team-b"),
                    ("ctx-a", "default"),
                ),
            ),
        )

        clusters = get_clusters_from_backend_config(config)

        assert len(clusters) == 1
        cluster = clusters[0]
        assert isinstance(cluster, Cluster)
        assert cluster.context_name == "ctx-a"
        assert cluster.region == ""
        assert cluster.namespace == "default"
        assert cluster.proxy_jump == KubernetesProxyJumpConfig()
        assert cluster.api_client.configuration.host == "https://ctx-a.example.com:6443"  # pyright: ignore[reportAttributeAccessIssue]

    def test_single_context_uses_namespace_from_backend_config(self):
        config = self.make_config(
            self.make_kubeconfig(contexts=(("ctx-a", "team-a"),)),
            namespace="team-a",
        )

        clusters = get_clusters_from_backend_config(config)

        assert clusters[0].namespace == "team-a"

    def test_single_context_defaults_namespace_when_not_set(self):
        config = self.make_config(
            self.make_kubeconfig(contexts=(("ctx-a", "team-a"),)),
            namespace=None,
        )

        clusters = get_clusters_from_backend_config(config)

        assert clusters[0].namespace == "default"

    def test_single_context_uses_proxy_jump_from_backend_config(self):
        proxy_jump = KubernetesProxyJumpConfig(hostname="1.2.3.4", port=2222)
        config = self.make_config(
            self.make_kubeconfig(),
            proxy_jump=proxy_jump,
        )

        clusters = get_clusters_from_backend_config(config)

        assert clusters[0].proxy_jump == proxy_jump

    def test_single_context_uses_default_proxy_jump_when_unset(self):
        config = self.make_config(self.make_kubeconfig(), proxy_jump=None)

        clusters = get_clusters_from_backend_config(config)

        assert clusters[0].proxy_jump == KubernetesProxyJumpConfig()

    def test_single_context_warns_on_namespace_mismatch(self, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.WARNING)
        config = self.make_config(
            self.make_kubeconfig(contexts=(("ctx-a", "kube-ns"),)),
            namespace="config-ns",
        )

        clusters = get_clusters_from_backend_config(config)

        assert clusters[0].namespace == "config-ns"
        assert "Namespace mismatch" in caplog.text
        assert "kube-ns" in caplog.text
        assert "config-ns" in caplog.text

    def test_single_context_does_not_warn_when_namespace_matches(
        self, caplog: pytest.LogCaptureFixture
    ):
        caplog.set_level(logging.WARNING)
        config = self.make_config(
            self.make_kubeconfig(contexts=(("ctx-a", "team-a"),)),
            namespace="team-a",
        )

        get_clusters_from_backend_config(config)

        assert "Namespace mismatch" not in caplog.text

    def test_single_context_raises_when_current_context_missing(self):
        kubeconfig = dedent("""
            apiVersion: v1
            kind: Config
            clusters:
            - name: cluster-a
              cluster:
                server: https://a.example.com:6443
            contexts:
            - name: ctx-a
              context:
                cluster: cluster-a
                user: user-a
            users:
            - name: user-a
              user:
                token: t
        """)
        config = self.make_config(kubeconfig)

        with pytest.raises(ValueError, match="current-context is not set"):
            get_clusters_from_backend_config(config)

    def test_contexts_as_strings(self):
        config = self.make_config(
            self.make_kubeconfig(
                current_context="ctx-a",
                contexts=(
                    ("ctx-a", "ns-a"),
                    ("ctx-b", "ns-b"),
                ),
            ),
            contexts=["ctx-a", "ctx-b"],
        )

        clusters = get_clusters_from_backend_config(config)

        assert [c.context_name for c in clusters] == ["ctx-a", "ctx-b"]
        assert [c.region for c in clusters] == ["ctx-a", "ctx-b"]
        assert [c.namespace for c in clusters] == ["ns-a", "ns-b"]
        assert all(c.proxy_jump == KubernetesProxyJumpConfig() for c in clusters)
        assert clusters[0].api_client.configuration.host == "https://ctx-a.example.com:6443"  # pyright: ignore[reportAttributeAccessIssue]
        assert clusters[1].api_client.configuration.host == "https://ctx-b.example.com:6443"  # pyright: ignore[reportAttributeAccessIssue]

    def test_contexts_with_per_context_proxy_jump(self):
        proxy_jump_a = KubernetesProxyJumpConfig(hostname="a.example.com", port=2201)
        proxy_jump_b = KubernetesProxyJumpConfig(hostname="b.example.com", port=2202)
        config = self.make_config(
            self.make_kubeconfig(
                contexts=(
                    ("ctx-a", "ns-a"),
                    ("ctx-b", "ns-b"),
                ),
            ),
            contexts=[
                KubernetesContextConfig(name="ctx-a", proxy_jump=proxy_jump_a),
                KubernetesContextConfig(name="ctx-b", proxy_jump=proxy_jump_b),
            ],
        )

        clusters = get_clusters_from_backend_config(config)

        assert clusters[0].proxy_jump == proxy_jump_a
        assert clusters[1].proxy_jump == proxy_jump_b

    def test_contexts_mix_string_and_object(self):
        proxy_jump = KubernetesProxyJumpConfig(hostname="b.example.com", port=2222)
        config = self.make_config(
            self.make_kubeconfig(
                contexts=(
                    ("ctx-a", "ns-a"),
                    ("ctx-b", "ns-b"),
                ),
            ),
            contexts=[
                "ctx-a",
                KubernetesContextConfig(name="ctx-b", proxy_jump=proxy_jump),
            ],
        )

        clusters = get_clusters_from_backend_config(config)

        assert clusters[0].proxy_jump == KubernetesProxyJumpConfig()
        assert clusters[1].proxy_jump == proxy_jump

    def test_contexts_object_without_proxy_jump_uses_default(self):
        config = self.make_config(
            self.make_kubeconfig(contexts=(("ctx-a", "ns-a"),)),
            contexts=[KubernetesContextConfig(name="ctx-a", proxy_jump=None)],
        )

        clusters = get_clusters_from_backend_config(config)

        assert clusters[0].proxy_jump == KubernetesProxyJumpConfig()

    def test_contexts_ignores_backend_namespace_and_proxy_jump(self):
        config = self.make_config(
            self.make_kubeconfig(contexts=(("ctx-a", "kube-ns"),)),
            contexts=["ctx-a"],
            namespace="config-ns",
            proxy_jump=KubernetesProxyJumpConfig(hostname="ignored", port=1),
        )

        clusters = get_clusters_from_backend_config(config)

        assert clusters[0].namespace == "kube-ns"
        assert clusters[0].proxy_jump == KubernetesProxyJumpConfig()

    def test_contexts_does_not_warn_on_namespace_mismatch(self, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.WARNING)
        config = self.make_config(
            self.make_kubeconfig(contexts=(("ctx-a", "kube-ns"),)),
            contexts=["ctx-a"],
            namespace="config-ns",
        )

        get_clusters_from_backend_config(config)

        assert "Namespace mismatch" not in caplog.text

    def test_contexts_raises_for_unknown_context(self):
        config = self.make_config(
            self.make_kubeconfig(contexts=(("ctx-a", "ns-a"),)),
            contexts=["ctx-missing"],
        )

        with pytest.raises(ValueError, match="context ctx-missing not found"):
            get_clusters_from_backend_config(config)

    def test_empty_contexts_returns_no_clusters(self):
        config = self.make_config(
            self.make_kubeconfig(contexts=(("ctx-a", "ns-a"),)),
            contexts=[],
        )

        clusters = get_clusters_from_backend_config(config)

        assert clusters == []

    def test_request_timeout_and_retries_propagate_to_client(self):
        config = self.make_config(self.make_kubeconfig())

        clusters = get_clusters_from_backend_config(config, request_timeout=7, retries=5)

        api_client = clusters[0].api_client
        assert api_client.configuration.retries == 5  # pyright: ignore[reportAttributeAccessIssue]
        assert getattr(api_client, "_ApiClient__request_timeout", None) == 7
