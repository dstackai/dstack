from typing import Optional

import pytest

from dstack._internal.server.utils.settings import parse_hostname_port


class TestParseHostnamePort:
    @pytest.mark.parametrize(
        ["value", "expected_hostname", "expected_port"],
        [
            pytest.param("example.com", "example.com", None, id="domain"),
            pytest.param("example.com:22", "example.com", 22, id="domain-port"),
            pytest.param("10.0.0.1", "10.0.0.1", None, id="ipv4"),
            pytest.param(
                "[fd69:b03c:7b2:b68a:6eda:b557:9526:757]",
                "fd69:b03c:7b2:b68a:6eda:b557:9526:757",
                None,
                id="ipv6",
            ),
            pytest.param(
                "[fd69:b03c:7b2:b68a:6eda:b557:9526:757]:22",
                "fd69:b03c:7b2:b68a:6eda:b557:9526:757",
                22,
                id="ipv6-port",
            ),
        ],
    )
    def test_valid(self, value: str, expected_hostname: str, expected_port: Optional[int]):
        hostname, port = parse_hostname_port(value)
        assert hostname == expected_hostname
        assert port == expected_port

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("", id="empty-string"),
            pytest.param(":22", id="no-hostname"),
            pytest.param("fd69:b03c:7b2:b68a:6eda:b557:9526:757", id="ipv6-without-brackets"),
            pytest.param("example.com:port", id="non-integer-port"),
            pytest.param("example.com:1000000", id="port-out-of-range"),
        ],
    )
    def test_invalid(self, value: str):
        with pytest.raises(ValueError, match=r"must be valid HOSTNAME\[:PORT\]"):
            parse_hostname_port(value)
