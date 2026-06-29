import json
from urllib.parse import parse_qs, urlparse

import pytest

from dstack._internal.core.backends.vastai.api_client import VastAIAPIClient


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status {self.status_code}")


@pytest.fixture
def client():
    return VastAIAPIClient(api_key="test-key")


def _parse_call(call):
    """Return (path, query_dict) for a recorded get() call."""
    url = call.args[0] if call.args else call.kwargs["url"]
    parsed = urlparse(url)
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    if "params" in call.kwargs and call.kwargs["params"]:
        for k, v in call.kwargs["params"].items():
            query[k] = str(v)
    return parsed.path, query


def test_get_instances_uses_v1_endpoint_and_paginates(client, monkeypatch):
    pages = [
        {"instances": [{"id": 1}, {"id": 2}], "next_token": "tok-1"},
        {"instances": [{"id": 3}], "next_token": None},
    ]
    calls = []

    def fake_get(url, params=None):
        calls.append((url, dict(params or {})))
        return _FakeResponse(pages[len(calls) - 1])

    monkeypatch.setattr(client.s, "get", fake_get)

    instances = client.get_instances(cache_ttl=0)

    assert [i["id"] for i in instances] == [1, 2, 3]
    assert len(calls) == 2
    # First call hits v1 and includes select_filters={} and a limit.
    first_url, first_params = calls[0]
    assert "/api/v1/instances/" in first_url
    assert first_params["select_filters"] == "{}"
    assert first_params["limit"] == 25
    assert "after_token" not in first_params
    # Second call carries the next_token from the prior response.
    _, second_params = calls[1]
    assert second_params["after_token"] == "tok-1"


def test_get_instance_uses_v1_select_filters(client, monkeypatch):
    calls = []

    def fake_get(url, params=None):
        calls.append((url, params))
        return _FakeResponse(
            {"instances": [{"id": 42, "actual_status": "running"}], "next_token": None}
        )

    monkeypatch.setattr(client.s, "get", fake_get)

    instance = client.get_instance(42)

    assert instance == {"id": 42, "actual_status": "running"}
    assert len(calls) == 1
    url, params = calls[0]
    assert "/api/v1/instances/" in url
    assert json.loads(params["select_filters"]) == {"id": {"eq": 42}}
    assert params["limit"] == 1


def test_get_instance_returns_none_when_missing(client, monkeypatch):
    monkeypatch.setattr(
        client.s,
        "get",
        lambda url, params=None: _FakeResponse({"instances": [], "next_token": None}),
    )
    assert client.get_instance(99) is None


def test_destroy_instance_still_uses_v0(client, monkeypatch):
    calls = []

    def fake_delete(url):
        calls.append(url)
        return _FakeResponse({"success": True})

    monkeypatch.setattr(client.s, "delete", fake_delete)
    monkeypatch.setattr(client, "_invalidate_cache", lambda: None)

    assert client.destroy_instance(7) is True
    assert "/api/v0/instances/7/" in calls[0]
