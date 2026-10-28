from unittest.mock import Mock, patch

from dstack.api.server import APIClient


class TestAPIClientTransport:
    def test_mounts_unix_socket_adapter(self):
        session = Mock()
        adapter = Mock()
        with (
            patch("dstack.api.server.requests.session", return_value=session),
            patch("dstack.api.server.requests_unixsocket.UnixAdapter", return_value=adapter),
        ):
            client = APIClient("http+unix://%2Frun%2Fdstack%2Fserver.sock", token="token")

        assert client.base_url == "http+unix://%2Frun%2Fdstack%2Fserver.sock"
        session.mount.assert_called_once_with("http+unix://", adapter)
        session.headers.update.assert_any_call({"Authorization": "Bearer token"})

    def test_http_transport_does_not_mount_unix_socket_adapter(self):
        session = Mock()
        with (
            patch("dstack.api.server.requests.session", return_value=session),
            patch("dstack.api.server.requests_unixsocket.UnixAdapter") as adapter_class,
        ):
            client = APIClient("https://server.example.com/")

        assert client.base_url == "https://server.example.com"
        adapter_class.assert_not_called()
        session.mount.assert_not_called()
