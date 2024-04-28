from typing import Optional

import pytest

from dstack._internal.server.utils.routers import check_client_server_compatibility


class TestCheckClientServerCompatibility:
    @pytest.mark.parametrize("client_version", ["12.12.12", None])
    def test_returns_none_if_server_version_is_none(self, client_version: Optional[str]):
        assert (
            check_client_server_compatibility(
                client_version=client_version,
                server_version=None,
            )
            is None
        )

    @pytest.mark.parametrize(
        "client_version,server_version",
        [
            ("0.12.4", "0.12.4"),
            ("0.12.4", "0.12.5"),
            ("1.0.5", "1.0.6"),
            ("0.12.4", "0.12.5rc1"),
        ],
    )
    def test_returns_none_if_compatible(
        self, client_version: Optional[str], server_version: Optional[str]
    ):
        assert (
            check_client_server_compatibility(
                client_version=client_version,
                server_version=server_version,
            )
            is None
        )

    @pytest.mark.parametrize(
        "client_version,server_version",
        [
            ("0.12.4", "0.13.0"),
            ("0.12.0", "1.12.0"),
        ],
    )
    def test_returns_error_if_client_version_smaller(
        self, client_version: Optional[str], server_version: Optional[str]
    ):
        res = check_client_server_compatibility(
            client_version=client_version,
            server_version=server_version,
        )
        assert res is not None

    @pytest.mark.parametrize(
        "client_version,server_version",
        [
            # no forward-compatibility at all (see https://github.com/dstackai/dstack/issues/1162)
            ("0.12.5", "0.12.4"),
            ("0.13.0", "0.12.4"),
            ("1.12.0", "0.12.0"),
        ],
    )
    def test_returns_error_if_client_version_larger(
        self, client_version: Optional[str], server_version: Optional[str]
    ):
        res = check_client_server_compatibility(
            client_version=client_version,
            server_version=server_version,
        )
        assert res is not None

    @pytest.mark.parametrize(
        "server_version",
        [
            None,
            "0.1.12",
        ],
    )
    def test_returns_none_if_client_version_is_latest(self, server_version: Optional[str]):
        res = check_client_server_compatibility(
            client_version="latest",
            server_version=server_version,
        )
        assert res is None
