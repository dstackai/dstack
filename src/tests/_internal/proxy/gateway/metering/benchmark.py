"""Explicit local microbenchmark; not a production load/capacity guarantee."""

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx

from tests._internal.proxy.gateway.metering.harness import Harness


def distribution(samples):
    ordered = sorted(samples)
    return (
        {
            "count": len(ordered),
            "p50_ms": ordered[len(ordered) // 2] * 1000,
            "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] * 1000,
            "max_ms": max(ordered) * 1000,
        }
        if ordered
        else {}
    )


async def run(root):
    h = Harness(root)
    await h.start()
    try:
        semaphore = asyncio.Semaphore(20)
        first = []
        durations = []
        payload_sizes = []
        async with httpx.AsyncClient(base_url=h.gateway_url, timeout=30) as client:

            async def request(i):
                async with semaphore:
                    request_id = f"perf-{i}"
                    started = time.perf_counter()
                    size = 0
                    first_seen = False
                    async with client.stream(
                        "POST",
                        "/api/models/p/chat/completions",
                        headers={
                            "Authorization": "Bearer token-a",
                            "X-Test-Request-ID": request_id,
                        },
                        json={
                            "model": "model-a",
                            "user": request_id,
                            "messages": [{"role": "user", "content": "A"}],
                            "stream": True,
                            "stream_options": {"include_usage": True},
                        },
                    ) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_bytes():
                            if not first_seen:
                                first.append(time.perf_counter() - started)
                                first_seen = True
                            size += len(chunk)
                    durations.append(time.perf_counter() - started)
                    payload_sizes.append(size)
                    await h.wait_finalized(request_id)

            # Grow a persisted backlog, then measure forwarding while that backlog is checkpointed.
            for i in range(20):
                await request(i)
                await h.advance_clock()
            first.clear()
            durations.clear()
            payload_sizes.clear()
            started = time.perf_counter()
            await asyncio.gather(
                *(request(i) for i in range(20, 220)), h.ipc_command("checkpoint")
            )
            elapsed = time.perf_counter() - started
            await h.advance_clock()
        metrics = await h.ipc_command("metrics")
        page = await h.batches()
        counted = sum(e["completion_tokens"] for b in page["batches"] for e in b["entries"])
        assert counted == 220 * 3
        result = {
            "requests": 200,
            "concurrency": 20,
            "mode": "burst, fragmented SSE, Python Gateway path",
            "elapsed_seconds": elapsed,
            "achieved_rps": 200 / elapsed,
            "response_bytes_min": min(payload_sizes),
            "response_bytes_max": max(payload_sizes),
            "first_byte": distribution(first),
            "forwarding": distribution(durations),
            "gateway_loop_lag": distribution(metrics["loop_lag_seconds"]),
            "checkpoint": distribution(metrics["checkpoint_seconds"]),
            "gateway_peak_rss_bytes": metrics["peak_rss_bytes"],
            "pending_batches": len(page["batches"]),
        }
        (root / "benchmark.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    finally:
        await h.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True)
    asyncio.run(run(Path(parser.parse_args().artifacts)))


if __name__ == "__main__":
    main()
