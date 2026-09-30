import pytest
import requests

from dstack._internal.core.backends.hotaisle.api_client import API_URL, HotAisleAPIClient
from dstack._internal.core.errors import BackendError, NoCapacityError

BARE_METAL_URL = f"{API_URL}/teams/test-team/bare_metal/"
SERVER_URL = f"{BARE_METAL_URL}deployment-id/"


def _client() -> HotAisleAPIClient:
    return HotAisleAPIClient(api_key="test-key", team_handle="test-team")


class TestReserveBareMetalServer:
    def test_posts_specs_and_description(self, requests_mock):
        requests_mock.post(BARE_METAL_URL, json={"deployment_id": "deployment-id"})

        server_data = _client().reserve_bare_metal_server(
            specs={"cpu_cores": 104}, description="test-instance"
        )

        assert server_data == {"deployment_id": "deployment-id"}
        assert requests_mock.last_request.json() == {
            "specs": {"cpu_cores": 104},
            "description": "test-instance",
        }

    @pytest.mark.parametrize(
        ("status_code", "text"),
        [(403, "tenant limit exceeded"), (404, "no available servers")],
    )
    def test_raises_no_capacity(self, requests_mock, status_code, text):
        requests_mock.post(BARE_METAL_URL, status_code=status_code, text=text)

        with pytest.raises(NoCapacityError, match=text):
            _client().reserve_bare_metal_server(specs={}, description="test-instance")

    def test_raises_on_other_errors(self, requests_mock):
        requests_mock.post(BARE_METAL_URL, status_code=402)

        with pytest.raises(requests.HTTPError):
            _client().reserve_bare_metal_server(specs={}, description="test-instance")


class TestReleaseBareMetalServer:
    def test_forces_release(self, requests_mock):
        requests_mock.delete(SERVER_URL, status_code=204)

        _client().release_bare_metal_server("deployment-id")

        assert requests_mock.last_request.qs == {"force": ["true"]}

    def test_releases_without_force(self, requests_mock):
        requests_mock.delete(SERVER_URL, status_code=204)

        _client().release_bare_metal_server("deployment-id", force=False)

        assert requests_mock.last_request.qs == {}

    def test_raises_if_refused_without_force(self, requests_mock):
        requests_mock.delete(SERVER_URL, status_code=400, text="minimum usage requirement")

        with pytest.raises(BackendError, match="minimum usage requirement"):
            _client().release_bare_metal_server("deployment-id", force=False)

    def test_ignores_missing_server(self, requests_mock):
        requests_mock.delete(SERVER_URL, status_code=404)

        _client().release_bare_metal_server("deployment-id")

    def test_raises_on_other_errors(self, requests_mock):
        requests_mock.delete(SERVER_URL, status_code=400)

        with pytest.raises(requests.HTTPError):
            _client().release_bare_metal_server("deployment-id")
