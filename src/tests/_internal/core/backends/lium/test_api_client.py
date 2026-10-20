import pytest
import requests

from dstack._internal.core.backends.lium.api_client import API_URL, LiumAPIClient, LiumAPIError


class TestLiumAPIClient:
    def test_identity_uses_api_key_and_timeout(self, requests_mock):
        requests_mock.get(f"{API_URL}/users/me", json={"id": "user-id"})

        assert LiumAPIClient("test-key").get_user() == {"id": "user-id"}

        assert requests_mock.last_request.headers["X-API-Key"] == "test-key"
        assert requests_mock.last_request.timeout == 30

    def test_version_reports_provider_features(self, requests_mock):
        version = {"features": ["rent_idempotency"]}
        requests_mock.get(f"{API_URL}/version", json=version)

        assert LiumAPIClient("test-key").get_version() == version

    def test_rental_sends_payload_and_idempotency_key(self, requests_mock):
        requests_mock.post(f"{API_URL}/executors/node-id/rent", json={"pod_id": "pod-id"})
        client = LiumAPIClient("test-key")
        payload = {"pod_name": "dstack-job", "template_id": "template-id", "gpu_count": 2}

        assert client.rent_executor("node-id", payload, "rent-key") == {"pod_id": "pod-id"}

        assert requests_mock.last_request.json() == payload
        assert requests_mock.last_request.headers["Idempotency-Key"] == "rent-key"

    @pytest.mark.parametrize(
        ["method", "path", "payload"],
        [
            ("create_template", "/templates", {"docker_image": "registry.example/image:tag"}),
            (
                "create_docker_credential",
                "/docker-credentials/",
                {"docker_username": "user", "docker_password": "private-password"},
            ),
        ],
    )
    def test_create_posts_payload_once(self, requests_mock, method, path, payload):
        requests_mock.post(API_URL + path, json={"id": "resource-id"})

        assert getattr(LiumAPIClient("test-key"), method)(payload) == {"id": "resource-id"}

        assert requests_mock.last_request.json() == payload
        assert requests_mock.call_count == 1

    @pytest.mark.parametrize("error", [requests.ReadTimeout, requests.ConnectionError])
    def test_rental_transport_error_does_not_retry_or_expose_credentials(
        self, requests_mock, error
    ):
        requests_mock.post(f"{API_URL}/executors/node-id/rent", exc=error("secret"))

        with pytest.raises(LiumAPIError) as exc:
            LiumAPIClient("secret").rent_executor("node-id", {"pod_name": "job"}, "rent-key")

        assert exc.value.status_code is None
        assert "secret" not in str(exc.value)
        assert exc.value.__suppress_context__
        assert requests_mock.call_count == 1

    @pytest.mark.parametrize("status", [401, 403, 409, 429, 503])
    def test_http_error_preserves_status_and_code_without_body(self, requests_mock, status):
        requests_mock.post(
            f"{API_URL}/executors/node-id/rent",
            status_code=status,
            json={"error": {"code": "idempotency_outcome_unknown", "message": "secret"}},
        )

        with pytest.raises(LiumAPIError) as exc:
            LiumAPIClient("secret").rent_executor("node-id", {"pod_name": "job"}, "rent-key")

        assert str(exc.value) == (f"Lium API returned HTTP {status} (idempotency_outcome_unknown)")
        assert exc.value.status_code == status
        assert exc.value.code == "idempotency_outcome_unknown"
        assert requests_mock.call_count == 1

    @pytest.mark.parametrize(
        "code", ["node_unavailable\nsecret", "x" * 65, {"detail": "secret"}, "lium_api_secret"]
    )
    def test_error_omits_malformed_codes_and_reflected_api_key(self, requests_mock, code):
        requests_mock.get(
            f"{API_URL}/users/me",
            status_code=403,
            json={"error": {"code": code, "message": "private credentials"}},
        )

        with pytest.raises(LiumAPIError) as exc:
            LiumAPIClient("lium_api_secret").get_user()

        assert str(exc.value) == "Lium API returned HTTP 403"
        assert exc.value.code is None

    def test_get_pod_returns_none_only_for_missing_pod(self, requests_mock):
        requests_mock.get(f"{API_URL}/pods/pod-id", json={"id": "pod-id", "status": "PENDING"})
        requests_mock.get(f"{API_URL}/pods/missing", status_code=404)
        requests_mock.get(f"{API_URL}/pods/forbidden", status_code=403)
        client = LiumAPIClient("test-key")

        assert client.get_pod("pod-id") == {"id": "pod-id", "status": "PENDING"}
        assert client.get_pod("missing") is None
        with pytest.raises(LiumAPIError) as exc:
            client.get_pod("forbidden")
        assert exc.value.status_code == 403

    @pytest.mark.parametrize("since", [None, "2026-10-16T08:00:00Z"])
    def test_account_events_include_deleted_pods_and_request_maximum_history(
        self, requests_mock, since
    ):
        event = {
            "pod_id": "pod-id",
            "pod_name": "dstack-job",
            "event_type": "pod-lifecycle",
            "to_status": "DELETED",
        }
        requests_mock.get(f"{API_URL}/users/me/events", json=[event])

        assert LiumAPIClient("test-key").get_account_events(since) == [event]

        params = {"limit": ["1000"]}
        if since is not None:
            params["since"] = [since.lower()]
        assert requests_mock.last_request.qs == params

    @pytest.mark.parametrize(
        ["headers", "expected"],
        [
            ({}, False),
            ({"Idempotent-Replayed": "false"}, False),
            ({"Idempotent-Replayed": "true"}, True),
        ],
    )
    def test_refusal_exposes_idempotent_replay_header(self, requests_mock, headers, expected):
        requests_mock.post(
            f"{API_URL}/executors/node-id/rent",
            status_code=400,
            headers=headers,
            json={"error": {"code": "node_unavailable"}},
        )

        with pytest.raises(LiumAPIError) as exc:
            LiumAPIClient("test-key").rent_executor("node-id", {"pod_name": "job"}, "rent-key")

        assert exc.value.idempotent_replayed is expected
        assert requests_mock.call_count == 1

    def test_volume_create_and_lookup(self, requests_mock):
        volume = {"id": "volume-id", "name": "checkpoints"}
        requests_mock.post(f"{API_URL}/volumes", json=volume)
        requests_mock.get(f"{API_URL}/volumes/volume-id", json=volume)
        requests_mock.get(f"{API_URL}/volumes/missing", status_code=404)
        requests_mock.get(
            f"{API_URL}/volumes/forbidden",
            status_code=403,
            json={"success": False, "message": "secret"},
        )
        client = LiumAPIClient("test-key")

        assert client.create_volume("checkpoints") == volume
        assert requests_mock.last_request.json() == {"name": "checkpoints"}
        assert client.get_volume("volume-id") == volume
        assert client.get_volume("missing") is None
        with pytest.raises(LiumAPIError) as exc:
            client.get_volume("forbidden")
        assert exc.value.status_code == 403
        assert exc.value.code is None
        assert "secret" not in str(exc.value)

    @pytest.mark.parametrize(
        ["method", "path"],
        [
            ("get_pods", "/pods"),
            ("get_templates", "/templates"),
        ],
    )
    def test_lists_require_object_items(self, requests_mock, method, path):
        requests_mock.get(
            API_URL + path, [{"json": [{"id": "resource-id"}]}, {"json": ["invalid"]}]
        )
        call = getattr(LiumAPIClient("test-key"), method)

        assert call() == [{"id": "resource-id"}]
        with pytest.raises(LiumAPIError, match="invalid list response"):
            call()

    @pytest.mark.parametrize(
        ["method", "path", "status"],
        [
            ("delete_pod", "/pods/resource-id", 200),
            ("delete_template", "/templates/resource-id", 204),
            ("delete_docker_credential", "/docker-credentials/resource-id", 404),
            ("delete_volume", "/volumes/resource-id", 404),
        ],
    )
    def test_delete_is_idempotent(self, requests_mock, method, path, status):
        requests_mock.delete(API_URL + path, status_code=status)

        getattr(LiumAPIClient("test-key"), method)("resource-id")

        assert requests_mock.call_count == 1

    def test_delete_error_is_not_silenced(self, requests_mock):
        requests_mock.delete(f"{API_URL}/pods/pod-id", status_code=503, text="secret")

        with pytest.raises(LiumAPIError) as exc:
            LiumAPIClient("test-key").delete_pod("pod-id")

        assert exc.value.status_code == 503
        assert str(exc.value) == "Lium API returned HTTP 503"

    def test_redirect_does_not_forward_api_key(self, requests_mock):
        requests_mock.get(
            f"{API_URL}/users/me",
            status_code=302,
            headers={"Location": "https://untrusted.example/identity"},
        )

        with pytest.raises(LiumAPIError) as exc:
            LiumAPIClient("test-key").get_user()

        assert exc.value.status_code == 302
        assert requests_mock.call_count == 1

    @pytest.mark.parametrize("body", ["not JSON", "null"])
    def test_invalid_create_response_does_not_retry(self, requests_mock, body):
        requests_mock.post(f"{API_URL}/templates", text=body)

        with pytest.raises(LiumAPIError):
            LiumAPIClient("test-key").create_template({"docker_image": "ubuntu:24.04"})

        assert requests_mock.call_count == 1
