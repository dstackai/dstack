import httpx
import pytest
from pydantic import ValidationError

from dstack._internal.server.services.gateways.client import AsyncClientWrapper, GatewayClient


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [1, 2])
async def test_usage_client_contract(version):
    seen = []

    def response(request):
        seen.append(request)
        if request.method == "GET":
            assert request.url.path == "/api/usage/batches" and request.url.params["limit"] == "2"
            return httpx.Response(
                200,
                json={
                    "schema_version": version,
                    "batches": [],
                    "has_more": False,
                    **({"collector_id": "c"} if version == 1 else {}),
                },
            )
        assert request.url.path == "/api/usage/batches/ack"
        return httpx.Response(200, json={"acknowledged_batch_ids": ["b"]})

    client = GatewayClient(port=1)
    await client._client.aclose()
    async with AsyncClientWrapper(transport=httpx.MockTransport(response)) as http:
        client._client = http
        page = await client.fetch_usage_batches(2)
        assert page.schema_version == 2
        assert "collector_id" not in page.model_dump()
        assert (await client.acknowledge_usage(["b"])).acknowledged_batch_ids == ["b"]
        assert all(r.extensions["timeout"]["read"] == 10 for r in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [404, 405, 503])
async def test_usage_client_http_errors(code):
    client = GatewayClient(port=1)
    await client._client.aclose()
    async with AsyncClientWrapper(
        transport=httpx.MockTransport(lambda r: httpx.Response(code))
    ) as http:
        client._client = http
        with pytest.raises(httpx.HTTPStatusError):
            await client.fetch_usage_batches()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", [{}, {"schema_version": 3}, {"schema_version": 2, "collector_id": "spoofed"}]
)
async def test_usage_client_rejects_malformed_data(payload):
    client = GatewayClient(port=1)
    await client._client.aclose()
    async with AsyncClientWrapper(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    ) as http:
        client._client = http
        with pytest.raises(ValidationError):
            await client.fetch_usage_batches()
