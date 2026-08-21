import pytest
import requests

from dstack._internal.core.backends.seeweb.api_client import API_URL, SeewebApiClient
from dstack._internal.core.errors import (
    BackendError,
    BackendInvalidCredentialsError,
    NoCapacityError,
)


def test_validate_api_key_and_auth_header(requests_mock):
    requests_mock.get(f"{API_URL}/regions", json={"status": "ok", "regions": []})

    assert SeewebApiClient("token").validate_api_key() is True
    assert requests_mock.last_request.headers["X-APITOKEN"] == "token"


def test_validate_api_key_returns_false_for_unauthorized(requests_mock):
    requests_mock.get(f"{API_URL}/regions", status_code=401, json={"message": "unauthorized"})

    assert SeewebApiClient("bad").validate_api_key() is False


def test_request_wraps_network_errors(requests_mock):
    requests_mock.get(f"{API_URL}/regions", exc=requests.ConnectTimeout("timed out"))

    with pytest.raises(BackendError, match="Seeweb API request failed"):
        SeewebApiClient("token").validate_api_key()


def test_forbidden_raises_invalid_credentials(requests_mock):
    requests_mock.get(f"{API_URL}/servers/server", status_code=403, text="forbidden")

    with pytest.raises(BackendInvalidCredentialsError):
        SeewebApiClient("bad").get_server("server")


def test_get_available_plans_parses_regions_and_active_images(requests_mock):
    requests_mock.get(
        f"{API_URL}/plans/availables",
        json={
            "status": "ok",
            "plans": [
                {
                    "name": "ECS1GPU7",
                    "region_availables": [{"region": "it-fr2"}],
                    "os_availables": [
                        {
                            "name": "ubuntu-2204-uefi-nvidia-driver",
                            "active_flag": True,
                        },
                        {"name": "old-image", "active_flag": False},
                    ],
                },
                {
                    "name": "ECS1GPU12",
                    "region_available": [{"region": "it-mi2"}],
                    "os_availables": [],
                },
            ],
        },
    )

    plans = SeewebApiClient("token").get_available_plans()

    assert plans["ECS1GPU7"].regions == frozenset({"it-fr2"})
    assert plans["ECS1GPU7"].images == ("ubuntu-2204-uefi-nvidia-driver",)
    assert plans["ECS1GPU12"].regions == frozenset({"it-mi2"})
    assert SeewebApiClient("token").get_available_plan_regions() == {
        ("ECS1GPU7", "it-fr2"),
        ("ECS1GPU12", "it-mi2"),
    }


def test_get_or_create_ssh_key_reuses_key_ignoring_comment(requests_mock):
    requests_mock.get(
        f"{API_URL}/sshkeys",
        json={
            "status": "ok",
            "pubkeys": [
                {
                    "label": "existing",
                    "key": "ssh-ed25519 AAAATEST old-comment",
                }
            ],
        },
    )

    label = SeewebApiClient("token").get_or_create_ssh_key("ssh-ed25519 AAAATEST new-comment")

    assert label == "existing"
    assert requests_mock.call_count == 1


def test_get_or_create_ssh_key_creates_missing_key(requests_mock):
    requests_mock.get(f"{API_URL}/sshkeys", json={"status": "ok", "pubkeys": []})
    requests_mock.post(f"{API_URL}/sshkeys", json={"status": "ok"})
    public_key = "ssh-ed25519 AAAATEST comment with spaces"

    label = SeewebApiClient("token").get_or_create_ssh_key(public_key)

    assert label.startswith("dstack-")
    assert requests_mock.last_request.json() == {"key": public_key, "label": label}


def test_get_or_create_ssh_key_rejects_invalid_key(requests_mock):
    with pytest.raises(ValueError, match="Invalid SSH public key"):
        SeewebApiClient("token").get_or_create_ssh_key('invalid "key"')

    assert requests_mock.call_count == 0


def test_create_server_parses_action_id(requests_mock):
    requests_mock.post(
        f"{API_URL}/servers",
        json={
            "status": "ok",
            "action": 35,
            "server": {"name": "ec-test", "status": "Booting"},
        },
    )

    server, action_id = SeewebApiClient("token").create_server(
        {
            "plan": "ECS1GPU7",
            "image": "ubuntu-2204-uefi-nvidia-driver",
            "location": "it-fr2",
        }
    )

    assert server["name"] == "ec-test"
    assert action_id == 35


@pytest.mark.parametrize("status_code", [200, 400])
def test_create_server_maps_capacity_errors(requests_mock, status_code):
    requests_mock.post(
        f"{API_URL}/servers",
        status_code=status_code,
        json={"status": "error", "message": "Plan is not available in this region"},
    )

    with pytest.raises(NoCapacityError, match="not available"):
        SeewebApiClient("token").create_server({})


def test_create_server_maps_other_errors(requests_mock):
    requests_mock.post(
        f"{API_URL}/servers",
        status_code=500,
        json={"status": "error", "message": "internal failure"},
    )

    with pytest.raises(BackendError, match="internal failure"):
        SeewebApiClient("token").create_server({})


def test_get_action_and_server(requests_mock):
    requests_mock.get(
        f"{API_URL}/actions/35",
        json={"status": "ok", "action": {"id": 35, "status": "completed"}},
    )
    requests_mock.get(
        f"{API_URL}/servers/ec-test",
        json={"status": "ok", "server": {"name": "ec-test", "ipv4": "192.0.2.1"}},
    )
    client = SeewebApiClient("token")

    assert client.get_action(35)["status"] == "completed"
    assert client.get_server("ec-test")["ipv4"] == "192.0.2.1"


def test_delete_server_is_idempotent(requests_mock):
    requests_mock.delete(
        f"{API_URL}/servers/missing",
        status_code=404,
        json={"status": "error", "message": "not found"},
    )

    SeewebApiClient("token").delete_server("missing")
