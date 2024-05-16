from dstack._internal.utils.network import get_ip_from_network


class TestNetworkUtils:
    def test_get_ip_from_network_none(self):
        ret = get_ip_from_network(None, [])
        assert ret is None

    def test_get_ip_from_network_regular(self):
        ret = get_ip_from_network("192.168.1.0/24", ["192.168.1.23"])
        assert ret == "192.168.1.23"

    def test_get_ip_from_network_miss_network(self):
        ret = get_ip_from_network("192.168.1.1/32", ["192.168.1.23"])
        assert ret is None

    def test_get_ip_from_network_any_ip(self):
        addrs = ["192.168.1.23", "10.1.0.0"]
        ret = get_ip_from_network(None, addrs)
        assert ret in addrs

    def test_get_ip_from_network_no_ip(self):
        ret = get_ip_from_network("192.168.1.0/24", [])
        assert ret is None

    def test_get_ip_from_network_ipv6(self):
        ret = get_ip_from_network("192.168.1.0/24", ["fe80::8d91:ba6b:b24d:9b41%4"])
        assert ret is None
