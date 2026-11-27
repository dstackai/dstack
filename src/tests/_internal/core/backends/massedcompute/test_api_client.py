import traceback

import pytest
import requests

from dstack._internal.core.backends.massedcompute.api_client import API_URL, MassedComputeAPIClient
from dstack._internal.core.errors import ComputeError, VolumeDeletionPending


class TestLaunch:
    @pytest.mark.parametrize(
        "response",
        [
            {"status_code": 408},
            {"status_code": 502},
            {"status_code": 202, "json": {"response": "invalid"}},
        ],
    )
    def test_unconfirmed_launch(self, requests_mock, response):
        launch = requests_mock.post(f"{API_URL}/instance/launch", **response)
        assert MassedComputeAPIClient("test").launch("worker", "product", "true") is None
        assert launch.call_count == 1

    @pytest.mark.parametrize("response", [{"status_code": 409}, {"exc": requests.ConnectTimeout}])
    def test_rejected_or_unsent_launch(self, requests_mock, response):
        requests_mock.post(f"{API_URL}/instance/launch", **response)
        with pytest.raises(ComputeError):
            MassedComputeAPIClient("test").launch("worker", "product", "true")


class TestDeleteVolume:
    def test_retries_until_provider_confirms_deletion(self, requests_mock):
        requests_mock.delete(
            f"{API_URL}/storage-volumes/vol-id",
            [
                {"status_code": 409},
                {"status_code": 202, "json": {"result": {"deleted": False}}},
                {"status_code": 200, "json": {"result": {"deleted": True}}},
                {"status_code": 404},
            ],
        )
        client = MassedComputeAPIClient("test")
        for _ in range(2):
            with pytest.raises(VolumeDeletionPending):
                client.delete_volume("vol-id")
        client.delete_volume("vol-id")
        client.delete_volume("vol-id")


class TestGetInstance:
    def test_invalid_response_keeps_password_out_of_traceback(self, requests_mock):
        requests_mock.get(
            f"{API_URL}/instance/vm-id",
            json={"runningInstances": [{"uuid": "vm-id", "password": "vm-login-secret"}]},
        )
        with pytest.raises(ComputeError, match="Unexpected response") as result:
            MassedComputeAPIClient("test-key").get_instance("vm-id")

        assert "vm-login-secret" not in "".join(traceback.format_exception(result.value))
