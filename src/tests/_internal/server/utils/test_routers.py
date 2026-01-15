from typing import Optional

import packaging.version
import pytest
from fastapi import HTTPException

from dstack._internal.server.utils.routers import check_client_server_compatibility


class TestCheckClientServerCompatibility:
    @pytest.mark.parametrize(
        ("client_version", "server_version"),
        [
            ("0.12.5", "0.12.4"),
            ("0.12.5rc1", "0.12.4"),
            ("0.12.4rc1", "0.12.4"),
            ("0.12.4", "0.12.4"),
            ("0.12.4", "0.12.5"),
            ("0.12.4", "0.13.0"),
            ("0.12.4", "1.12.0"),
            ("0.12.4", "0.12.5rc1"),
            ("1.0.5", "1.0.6"),
            ("12.12.12", None),
            (None, "0.1.12"),
            (None, None),
        ],
    )
    def test_compatible(
        self, client_version: Optional[str], server_version: Optional[str]
    ) -> None:
        parsed_client_version = None
        if client_version is not None:
            parsed_client_version = packaging.version.parse(client_version)

        check_client_server_compatibility(
            client_version=parsed_client_version,
            server_version=server_version,
        )

    @pytest.mark.parametrize(
        ("client_version", "server_version"),
        [
            ("0.13.0", "0.12.4"),
            ("1.12.0", "0.12.0"),
        ],
    )
    def test_incompatible(self, client_version: str, server_version: str) -> None:
        with pytest.raises(HTTPException):
            check_client_server_compatibility(
                client_version=packaging.version.parse(client_version),
                server_version=server_version,
            )
