import pytest
import requests

from dstack._internal.core.backends.daytona.api_client import (
    API_URL,
    DaytonaAPIClient,
    DaytonaAPIError,
    DaytonaNotFoundError,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError, NoCapacityError

TOOLBOX_URL = "https://proxy.app.daytona.io/toolbox/sandbox-id"


class TestDaytonaAPIClient:
    def test_identity_uses_bearer_auth(self, requests_mock):
        requests_mock.get(
            f"{API_URL}/api-keys/current", json={"organizationId": "organization-id"}
        )

        identity = DaytonaAPIClient("test-api-key").get_current_api_key()

        assert identity["organizationId"] == "organization-id"
        assert requests_mock.last_request.headers["Authorization"] == "Bearer test-api-key"
        assert requests_mock.last_request.timeout == 30

    def test_unauthorized_maps_to_invalid_credentials(self, requests_mock):
        requests_mock.get(f"{API_URL}/api-keys/current", status_code=401)

        with pytest.raises(BackendInvalidCredentialsError) as exc:
            DaytonaAPIClient("bad-key").get_current_api_key()

        assert exc.value.fields == [["creds", "api_key"]]

    @pytest.mark.parametrize(
        ["status", "message"],
        [
            (400, "No capacity available"),
            (429, "Too many requests"),
            (503, "Service unavailable"),
        ],
    )
    def test_http_errors_preserve_status_and_reason(self, requests_mock, status, message):
        requests_mock.post(f"{API_URL}/sandbox", status_code=status, json={"message": message})

        with pytest.raises(DaytonaAPIError, match=message) as exc:
            DaytonaAPIClient("test-api-key").create_sandbox({"name": "test"})

        assert exc.value.status_code == status
        assert not isinstance(exc.value, NoCapacityError)
        assert requests_mock.call_count == 1

    def test_not_found_is_distinct(self, requests_mock):
        requests_mock.get(f"{API_URL}/organizations/missing/usage", status_code=404)

        with pytest.raises(DaytonaNotFoundError) as exc:
            DaytonaAPIClient("test-api-key").get_organization_usage("missing")

        assert exc.value.status_code == 404

    @pytest.mark.parametrize("error", [requests.ReadTimeout, requests.ConnectionError])
    def test_network_errors_preserve_cause_without_retrying(self, requests_mock, error):
        cause = error("Connection failed")
        requests_mock.post(f"{API_URL}/sandbox", exc=cause)
        client = DaytonaAPIClient("test-api-key")

        with pytest.raises(DaytonaAPIError) as exc:
            client.create_sandbox({"name": "test"})

        assert exc.value.__cause__ is cause
        assert exc.value.status_code is None
        assert requests_mock.call_count == 1

    def test_error_response_redacts_api_key(self, requests_mock):
        requests_mock.get(
            f"{API_URL}/api-keys/current",
            status_code=403,
            json={"message": "Denied for Bearer secret-api-key"},
        )

        with pytest.raises(DaytonaAPIError, match="Denied for Bearer \\[redacted\\]"):
            DaytonaAPIClient("secret-api-key").get_current_api_key()

    def test_non_json_error_omits_response_body(self, requests_mock):
        requests_mock.get(
            f"{API_URL}/api-keys/current", status_code=502, text="gateway HTML with credentials"
        )

        with pytest.raises(DaytonaAPIError) as exc:
            DaytonaAPIClient("test-api-key").get_current_api_key()

        assert str(exc.value) == "Daytona API returned HTTP 502"

    def test_redirect_is_not_followed(self, requests_mock):
        requests_mock.get(
            f"{API_URL}/api-keys/current",
            status_code=302,
            headers={"Location": "https://untrusted.example/identity"},
        )

        with pytest.raises(DaytonaAPIError) as exc:
            DaytonaAPIClient("test-api-key").get_current_api_key()

        assert exc.value.status_code == 302
        assert requests_mock.call_count == 1

    @pytest.mark.parametrize("body", ["not-json", "[]"])
    def test_invalid_identity_response(self, requests_mock, body):
        requests_mock.get(f"{API_URL}/api-keys/current", text=body)

        with pytest.raises(DaytonaAPIError):
            DaytonaAPIClient("test-api-key").get_current_api_key()

    @pytest.mark.parametrize("body", ["{}", '["eu"]'])
    def test_invalid_regions_response(self, requests_mock, body):
        requests_mock.get(f"{API_URL}/shared-regions", text=body)

        with pytest.raises(DaytonaAPIError, match="invalid list"):
            DaytonaAPIClient("test-api-key").get_shared_regions()

    def test_get_sandbox_accepts_id_or_name_and_returns_none_only_for_404(self, requests_mock):
        requests_mock.get(f"{API_URL}/sandbox/sandbox-id", json={"id": "sandbox-id"})
        requests_mock.get(f"{API_URL}/sandbox/job-name", json={"id": "sandbox-id"})
        requests_mock.get(f"{API_URL}/sandbox/missing", status_code=404)
        requests_mock.get(f"{API_URL}/sandbox/forbidden", status_code=403)
        client = DaytonaAPIClient("test-api-key")

        assert client.get_sandbox("sandbox-id") == {"id": "sandbox-id"}
        assert client.get_sandbox("job-name") == {"id": "sandbox-id"}
        assert client.get_sandbox("missing") is None
        with pytest.raises(DaytonaAPIError):
            client.get_sandbox("forbidden")

    def test_volume_create_lookup_and_deleted_tombstone(self, requests_mock):
        pending = {"id": "volume-id", "state": "pending_create"}
        deleted = {"id": "volume-id", "state": "deleted"}
        requests_mock.post(f"{API_URL}/volumes", json=pending)
        requests_mock.get(f"{API_URL}/volumes/by-name/volume-name", json=pending)
        requests_mock.get(f"{API_URL}/volumes/volume-id", json=deleted)
        requests_mock.get(f"{API_URL}/volumes/missing", status_code=404)
        requests_mock.get(f"{API_URL}/volumes/by-name/missing", status_code=404)
        client = DaytonaAPIClient("test-api-key")

        assert client.create_volume("volume-name") == pending
        assert requests_mock.last_request.json() == {"name": "volume-name"}
        assert client.get_volume_by_name("volume-name") == pending
        assert client.get_volume("volume-id") == deleted
        assert client.get_volume("missing") is None
        assert client.get_volume_by_name("missing") is None

    @pytest.mark.parametrize(
        ["method", "path", "status"],
        [
            ("delete_sandbox", "/sandbox/resource-id", 200),
            ("delete_registry", "/docker-registry/resource-id", 204),
            ("delete_volume", "/volumes/resource-id", 404),
        ],
    )
    def test_delete_endpoints_are_idempotent(self, requests_mock, method, path, status):
        requests_mock.delete(API_URL + path, status_code=status)

        getattr(DaytonaAPIClient("test-api-key"), method)("resource-id")

    @pytest.mark.parametrize(
        ["method", "path", "failure"],
        [
            ("delete_sandbox", "/sandbox/resource-id", {"status_code": 503}),
            ("delete_registry", "/docker-registry/resource-id", {"status_code": 429}),
            ("delete_volume", "/volumes/resource-id", {"exc": requests.ReadTimeout}),
        ],
    )
    def test_delete_retries_transient_errors(self, requests_mock, mocker, method, path, failure):
        sleep = mocker.patch("dstack._internal.core.backends.daytona.api_client.time.sleep")
        requests_mock.delete(API_URL + path, [failure, {"status_code": 404}])

        getattr(DaytonaAPIClient("test-api-key"), method)("resource-id")

        assert requests_mock.call_count == 2
        sleep.assert_called_once_with(1)

    def test_delete_stops_retrying_after_three_attempts(self, requests_mock, mocker):
        sleep = mocker.patch("dstack._internal.core.backends.daytona.api_client.time.sleep")
        requests_mock.delete(f"{API_URL}/docker-registry/registry-id", status_code=503)

        with pytest.raises(DaytonaAPIError) as exc:
            DaytonaAPIClient("test-api-key").delete_registry("registry-id")

        assert exc.value.status_code == 503
        assert requests_mock.call_count == 3
        assert [call.args[0] for call in sleep.call_args_list] == [1, 2]

    def test_delete_does_not_retry_permission_errors(self, requests_mock, mocker):
        sleep = mocker.patch("dstack._internal.core.backends.daytona.api_client.time.sleep")
        requests_mock.delete(f"{API_URL}/docker-registry/registry-id", status_code=403)

        with pytest.raises(DaytonaAPIError) as exc:
            DaytonaAPIClient("test-api-key").delete_registry("registry-id")

        assert exc.value.status_code == 403
        assert requests_mock.call_count == 1
        sleep.assert_not_called()

    def test_toolbox_url_includes_sandbox_id(self, requests_mock):
        requests_mock.get(
            f"{API_URL}/sandbox/sandbox-id/toolbox-proxy-url",
            json={"url": "https://proxy.app.daytona.io/toolbox/"},
        )

        assert DaytonaAPIClient("test-api-key").get_toolbox_url("sandbox-id") == TOOLBOX_URL

    @pytest.mark.parametrize(
        "url",
        [
            "http://proxy.app.daytona.io/toolbox",
            "https://daytona.io.attacker.example/toolbox",
            "https://attacker.example/toolbox",
            "https://user:password@proxy.app.daytona.io/toolbox",
            "https://proxy.app.daytona.io/toolbox?token=secret",
            "https://proxy.app.daytona.io:8443/toolbox",
        ],
    )
    def test_toolbox_rejects_untrusted_url_before_sending_credentials(self, requests_mock, url):
        with pytest.raises(DaytonaAPIError, match="invalid toolbox proxy URL"):
            DaytonaAPIClient("test-api-key").get_session(url, "runner")

        assert requests_mock.call_count == 0

    def test_session_creation_and_async_command(self, requests_mock):
        requests_mock.post(f"{TOOLBOX_URL}/process/session", status_code=201)
        requests_mock.post(
            f"{TOOLBOX_URL}/process/session/runner/exec", json={"cmdId": "command-id"}
        )
        client = DaytonaAPIClient("test-api-key")

        client.create_session(TOOLBOX_URL, "runner")
        command = client.execute_session_command(TOOLBOX_URL, "runner", "/tmp/dstack-runner start")

        assert requests_mock.request_history[0].json() == {"sessionId": "runner"}
        assert requests_mock.last_request.json() == {
            "command": "/tmp/dstack-runner start",
            "runAsync": True,
        }
        assert requests_mock.last_request.headers["Authorization"] == "Bearer test-api-key"
        assert command == {"cmdId": "command-id"}

    def test_missing_session(self, requests_mock):
        requests_mock.get(f"{TOOLBOX_URL}/process/session/runner", status_code=404)
        client = DaytonaAPIClient("test-api-key")

        assert client.get_session(TOOLBOX_URL, "runner") is None

    def test_ssh_access_preserves_explicit_long_lifetime(self, requests_mock):
        access = {
            "token": "ssh-access-token",
            "sshCommand": "ssh -p 2222 ssh-access-token@ssh.app.daytona.io",
            "expiresAt": "2027-09-28T00:00:00Z",
        }
        requests_mock.post(f"{API_URL}/sandbox/sandbox-id/ssh-access", json=access)

        result = DaytonaAPIClient("test-api-key").create_ssh_access(
            "sandbox-id", expires_in_minutes=365 * 24 * 60
        )

        assert result == access
        assert requests_mock.last_request.qs == {"expiresinminutes": ["525600"]}
