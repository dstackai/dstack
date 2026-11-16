"""Deterministic traffic with expectations independent of Gateway counters."""

import argparse
import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

FIXTURES = json.loads(Path(__file__).with_name("fixtures.json").read_text())


@dataclass
class TrafficReport:
    attempts: list[dict] = field(default_factory=list)


class TrafficDriver:
    def __init__(
        self, url: str, client: httpx.AsyncClient | None = None, artifact_dir: Path | None = None
    ):
        self.artifact_path = (
            artifact_dir / f"traffic-{uuid.uuid4().hex}.json" if artifact_dir else None
        )
        self.client = client or httpx.AsyncClient(base_url=url, timeout=30)
        self._owns_client = client is None
        self.report = TrafficReport()

    async def send(
        self,
        request_id: str,
        case: str = "A",
        token: str = "token-a",
        model: str = "model-a",
        stream: bool = False,
    ) -> dict:
        request = {
            "model": model,
            "messages": [{"role": "user", "content": case}],
            "user": request_id,
            "stream": stream,
        }
        if stream:
            request["stream_options"] = {"include_usage": True}
        headers = {"Authorization": f"Bearer {token}", "X-Test-Request-ID": request_id}
        async with self.client.stream(
            "POST", "/api/models/p/chat/completions", json=request, headers=headers
        ) as response:
            response.raise_for_status()
            if stream:
                events = []
                observed = None
                saw_done = False
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        saw_done = True
                        continue
                    data = json.loads(payload)
                    events.append(data)
                    if data.get("usage") is not None:
                        observed = data["usage"]
                raw = events
                if case != "cut":
                    assert saw_done, "stream missing completion marker"
            else:
                raw = json.loads(await response.aread())
                observed = raw.get("usage")
        expected = FIXTURES[case]
        if case == "cut":
            assert observed is None, "unexpected confirmed usage in interrupted stream"
            normalized = dict(expected)
        else:
            assert observed is not None, "missing usage"
            normalized = {
                "prompt_tokens": observed["prompt_tokens"],
                "cached_prompt_tokens": (observed.get("prompt_tokens_details") or {}).get(
                    "cached_tokens", 0
                ),
                "completion_tokens": observed["completion_tokens"],
                "total_tokens": observed["total_tokens"],
                "unknown_usage_attempts": 0,
            }
            assert normalized == expected, (
                f"usage mismatch for {request_id}: {normalized} != {expected}"
            )
        item = {
            "request_id": request_id,
            "case": case,
            "subject": {"token-a": "1" * 32, "token-b": "2" * 32}.get(token, "unknown"),
            "service": {"model-a": "a" * 32, "model-b": "b" * 32}[model],
            "expected": dict(expected),
            "observed": normalized,
            "response": raw,
        }
        self.report.attempts.append(item)
        return item

    async def run(self, manifest: list[dict]) -> TrafficReport:
        await asyncio.gather(*(self.send(**item) for item in manifest))
        return self.report

    async def close(self) -> None:
        if self.artifact_path is not None:
            self.artifact_path.write_text(json.dumps(self.report.attempts, indent=2))
        if self._owns_client:
            await self.client.aclose()


async def _run(args) -> None:
    driver = TrafficDriver(args.url)
    try:
        await driver.run(
            [
                dict(request_id=f"{args.case}-{i}", case=args.case, stream=args.stream)
                for i in range(args.count)
            ]
        )
        print(json.dumps(driver.report.attempts, indent=2))
    finally:
        await driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--case", choices=list(FIXTURES), default="A")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--stream", action="store_true")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
