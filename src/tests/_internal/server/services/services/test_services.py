from typing import Literal, Optional, Union
from unittest.mock import MagicMock

import pytest

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.gateways import (
    ACMGatewayCertificate,
    AnyGatewayCertificate,
    GatewayConfiguration,
    LetsEncryptGatewayCertificate,
)
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.services.services import (
    _get_service_https,
    _register_service_in_server,
)
from dstack._internal.server.testing.common import get_run_spec


def _service_run_spec(https: Union[bool, Literal["auto"]] = "auto") -> RunSpec:
    return get_run_spec(
        repo_id="test-repo",
        configuration=ServiceConfiguration(commands=["python serve.py"], port=8000, https=https),
    )


def _gateway_config(
    certificate: Optional[AnyGatewayCertificate] = LetsEncryptGatewayCertificate(),
) -> GatewayConfiguration:
    return GatewayConfiguration(
        backend=BackendType.AWS,
        region="us-east-1",
        certificate=certificate,
    )


def _mock_run_model() -> MagicMock:
    run_model = MagicMock()
    run_model.project.name = "test-project"
    run_model.run_name = "test-run"
    return run_model


class TestServiceConfigurationHttps:
    def test_accepts_unset(self) -> None:
        conf = ServiceConfiguration(commands=["python serve.py"], port=8000)
        assert conf.https is None

    def test_accepts_auto(self) -> None:
        conf = ServiceConfiguration(commands=["python serve.py"], port=8000, https="auto")
        assert conf.https == "auto"


class TestGetServiceHttps:
    def test_auto_resolves_to_true_with_lets_encrypt_gateway(self) -> None:
        run_spec = _service_run_spec(https="auto")
        gw = _gateway_config(certificate=LetsEncryptGatewayCertificate())
        assert _get_service_https(run_spec, gw) is True

    def test_auto_resolves_to_false_when_gateway_has_no_certificate(self) -> None:
        run_spec = _service_run_spec(https="auto")
        gw = _gateway_config(certificate=None)
        assert _get_service_https(run_spec, gw) is False

    def test_auto_resolves_to_false_with_acm_gateway(self) -> None:
        run_spec = _service_run_spec(https="auto")
        gw = _gateway_config(
            certificate=ACMGatewayCertificate(arn="arn:aws:acm:us-east-1:123:cert/abc")
        )
        assert _get_service_https(run_spec, gw) is False

    def test_true_enables_https_regardless_of_gateway_certificate(self) -> None:
        run_spec = _service_run_spec(https=True)
        gw = _gateway_config(certificate=None)
        assert _get_service_https(run_spec, gw) is True

    def test_false_disables_https_regardless_of_gateway_certificate(self) -> None:
        run_spec = _service_run_spec(https=False)
        gw = _gateway_config(certificate=LetsEncryptGatewayCertificate())
        assert _get_service_https(run_spec, gw) is False


class TestRegisterServiceInServerHttps:
    def test_allows_default_true_without_gateway(self) -> None:
        run_spec = _service_run_spec(https=True)
        result = _register_service_in_server(_mock_run_model(), run_spec)
        assert result is not None

    def test_allows_auto_without_gateway(self) -> None:
        run_spec = _service_run_spec(https="auto")
        result = _register_service_in_server(_mock_run_model(), run_spec)
        assert result is not None

    def test_rejects_explicit_false_without_gateway(self) -> None:
        run_spec = _service_run_spec(https=False)
        with pytest.raises(ServerClientError, match="not allowed without a gateway"):
            _register_service_in_server(_mock_run_model(), run_spec)
