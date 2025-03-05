from unittest.mock import Mock, patch

import pytest

from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends.kubernetes import (
    KubeconfigConfig,
    KubernetesConfigInfoWithCreds,
    KubernetesNetworkingConfig,
)
from dstack._internal.server.services.backends.configurators.kubernetes import (
    KubernetesConfigurator,
)


class TestKubernetesConfigurator:
    def test_validate_config_valid(self):
        config = KubernetesConfigInfoWithCreds(
            kubeconfig=KubeconfigConfig(data="valid", filename="-"),
            networking=KubernetesNetworkingConfig(ssh_host=None, ssh_port=None),
        )
        with patch(
            "dstack._internal.core.backends.kubernetes.utils.get_api_from_config_data"
        ) as get_api_mock:
            api_mock = Mock()
            api_mock.list_node.return_value = Mock()
            get_api_mock.return_value = api_mock
            KubernetesConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_config(self):
        config = KubernetesConfigInfoWithCreds(
            kubeconfig=KubeconfigConfig(data="invalid", filename="-"),
            networking=KubernetesNetworkingConfig(ssh_host=None, ssh_port=None),
        )
        with (
            patch(
                "dstack._internal.core.backends.kubernetes.utils.get_api_from_config_data"
            ) as get_api_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            get_api_mock.side_effect = Exception("Invalid config")
            KubernetesConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["kubeconfig"]]
