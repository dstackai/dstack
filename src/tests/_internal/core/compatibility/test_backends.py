import json

import pytest

from dstack._internal.core.backends.gcp.models import GCPBackendConfigWithCreds, GCPDefaultCreds
from dstack._internal.core.backends.hotaisle.models import (
    HotAisleAPIKeyCreds,
    HotAisleBackendConfigWithCreds,
)
from dstack._internal.core.backends.kubernetes.models import (
    KubeconfigConfig,
    KubernetesBackendConfigWithCreds,
    KubernetesContextConfig,
    KubernetesProxyJumpConfig,
)
from dstack._internal.core.backends.models import AnyBackendConfigWithCreds
from dstack._internal.core.compatibility.backends import get_backend_config_excludes


def _request_body(config: AnyBackendConfigWithCreds) -> dict:
    return json.loads(config.model_dump_json(exclude=get_backend_config_excludes(config)))


class TestGetBackendConfigExcludes:
    def test_excludes_unset_gcp_tpu(self):
        config = GCPBackendConfigWithCreds(project_id="test-project", creds=GCPDefaultCreds())

        assert "tpu" not in _request_body(config)

    @pytest.mark.parametrize("tpu", [False, True])
    def test_keeps_set_gcp_tpu(self, tpu):
        config = GCPBackendConfigWithCreds(
            project_id="test-project", creds=GCPDefaultCreds(), tpu=tpu
        )

        assert _request_body(config)["tpu"] is tpu

    def test_excludes_unset_hotaisle_bare_metal(self):
        config = HotAisleBackendConfigWithCreds(
            team_handle="test-team", creds=HotAisleAPIKeyCreds(api_key="test-key")
        )

        assert "bare_metal" not in _request_body(config)

    def test_keeps_set_hotaisle_bare_metal(self):
        config = HotAisleBackendConfigWithCreds(
            team_handle="test-team", creds=HotAisleAPIKeyCreds(api_key="test-key"), bare_metal=True
        )

        assert _request_body(config)["bare_metal"] is True

    def test_excludes_unset_kubernetes_proxy_jump_resources(self):
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked"),
            proxy_jump=KubernetesProxyJumpConfig(hostname="203.0.113.1"),
        )

        assert _request_body(config)["proxy_jump"] == {"hostname": "203.0.113.1", "port": None}

    def test_keeps_set_kubernetes_proxy_jump_resources(self):
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked"),
            proxy_jump=KubernetesProxyJumpConfig(cpu="1"),
        )

        assert _request_body(config)["proxy_jump"] == {"hostname": None, "port": None, "cpu": "1"}

    def test_keeps_set_kubernetes_proxy_jump_placement(self):
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked"),
            proxy_jump=KubernetesProxyJumpConfig(node_selector=["pool=cpu"], tolerations=[]),
        )

        assert _request_body(config)["proxy_jump"] == {
            "hostname": None,
            "port": None,
            "node_selector": ["pool=cpu"],
            "tolerations": [],
        }

    def test_excludes_unset_kubernetes_context_proxy_jump_resources(self):
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked"),
            contexts=[
                "ctx-1",
                KubernetesContextConfig(name="ctx-2"),
                KubernetesContextConfig(
                    name="ctx-3", proxy_jump=KubernetesProxyJumpConfig(hostname="203.0.113.1")
                ),
            ],
        )

        assert _request_body(config)["contexts"] == [
            "ctx-1",
            {"name": "ctx-2", "proxy_jump": None},
            {"name": "ctx-3", "proxy_jump": {"hostname": "203.0.113.1", "port": None}},
        ]

    def test_keeps_kubernetes_context_proxy_jump_resources_set_in_any_context(self):
        # A field set in one context is sent for all contexts, as only newer servers accept it
        config = KubernetesBackendConfigWithCreds(
            kubeconfig=KubeconfigConfig(data="mocked"),
            contexts=[
                KubernetesContextConfig(
                    name="ctx-1", proxy_jump=KubernetesProxyJumpConfig(cpu="1")
                ),
                KubernetesContextConfig(
                    name="ctx-2", proxy_jump=KubernetesProxyJumpConfig(memory="2Gi")
                ),
            ],
        )

        assert _request_body(config)["contexts"] == [
            {
                "name": "ctx-1",
                "proxy_jump": {"hostname": None, "port": None, "cpu": "1", "memory": None},
            },
            {
                "name": "ctx-2",
                "proxy_jump": {"hostname": None, "port": None, "cpu": None, "memory": "2Gi"},
            },
        ]
