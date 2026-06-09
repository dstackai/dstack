import uuid
from datetime import datetime, timezone

from packaging.version import Version

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import (
    Gateway,
    GatewayConfiguration,
    GatewayReplica,
    GatewayStatus,
)
from dstack._internal.server.compatibility.gateways import patch_gateway
from dstack._internal.utils.common import get_current_datetime

_CREATED_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)
_CONFIG = GatewayConfiguration(name="gw", backend=BackendType.AWS, region="us")


def _make_gateway_replica(hostname: str = "1.2.3.4") -> GatewayReplica:
    return GatewayReplica(
        hostname=hostname,
        replica_num=0,
        backend=BackendType.AWS,
        region="us",
        created_at=get_current_datetime(),
    )


def _make_gateway(replicas=None, hostname=None) -> Gateway:
    return Gateway(
        id=uuid.uuid4(),
        name="test",
        project_name="proj",
        backend=BackendType.AWS,
        region="us",
        created_at=_CREATED_AT,
        status=GatewayStatus.RUNNING,
        status_message=None,
        hostname=hostname,
        wildcard_domain=None,
        default=False,
        replicas=replicas or [],
        configuration=_CONFIG,
    )


class TestPatchGateway:
    def test_none_version_is_noop(self):
        replica = _make_gateway_replica("1.2.3.4")
        gw = _make_gateway(replicas=[replica])
        patch_gateway(gw, None)
        assert gw.ip_address is None
        assert gw.instance_id is None
        assert gw.hostname is None

    def test_new_version_is_noop(self):
        replica = _make_gateway_replica("1.2.3.4")
        gw = _make_gateway(replicas=[replica])
        patch_gateway(gw, Version("0.20.25"))
        assert gw.ip_address is None
        assert gw.instance_id is None

    def test_old_version_fills_hostname_from_replica(self):
        replica = _make_gateway_replica("1.2.3.4")
        gw = _make_gateway(replicas=[replica], hostname=None)
        patch_gateway(gw, Version("0.20.24"))
        assert gw.hostname == "1.2.3.4"

    def test_old_version_keeps_existing_hostname(self):
        replica = _make_gateway_replica("1.2.3.4")
        gw = _make_gateway(replicas=[replica], hostname="lb.example.com")
        patch_gateway(gw, Version("0.20.24"))
        assert gw.hostname == "lb.example.com"

    def test_old_version_no_replicas_sets_empty_strings(self):
        gw = _make_gateway(replicas=[])
        patch_gateway(gw, Version("0.20.24"))
        assert gw.ip_address == ""
        assert gw.instance_id == ""
        assert gw.hostname == ""

    def test_old_version_multi_replica_is_noop(self):
        replicas = [_make_gateway_replica("1.2.3.4"), _make_gateway_replica("5.6.7.8")]
        gw = _make_gateway(replicas=replicas)
        patch_gateway(gw, Version("0.20.24"))
        assert gw.ip_address is None
        assert gw.instance_id is None
