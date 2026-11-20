"""Local deterministic inference + server authorization fixture; never shipped as an API."""

import asyncio
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from tests._internal.proxy.gateway.metering.traffic import FIXTURES

SUBJECTS = {"token-a": "1" * 32, "token-b": "2" * 32}


def make_backend() -> FastAPI:
    app = FastAPI()
    holds: dict[str, asyncio.Event] = {}
    after_usage: set[str] = set()
    started: set[str] = set()

    @app.get("/")
    async def ready():
        return {"ready": True}

    @app.post("/api/projects/{project}/get")
    @app.post("/api/projects/{project}/authorize_proxy")
    async def authorize(project: str, request: Request):
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if project != "p" or token not in SUBJECTS:
            raise HTTPException(403)
        return {"consumer_subject_id": SUBJECTS[token]}

    @app.post("/test/control")
    async def control(request: Request):
        body = await request.json()
        for request_id in body.get("hold", []):
            holds[request_id] = asyncio.Event()
            if body.get("after_usage"):
                after_usage.add(request_id)
        for request_id in body.get("release", []):
            if request_id in holds:
                holds[request_id].set()
        return {"started": sorted(started)}

    @app.post("/v1/chat/completions")
    async def completions(request: Request):
        body = await request.json()
        request_id = body["user"]
        started.add(request_id)
        case = body["messages"][0]["content"]
        expected = FIXTURES[case]
        usage = {
            "prompt_tokens": expected["prompt_tokens"],
            "completion_tokens": expected["completion_tokens"],
            "total_tokens": expected["total_tokens"],
            "prompt_tokens_details": (
                {"cached_tokens": expected["cached_prompt_tokens"]}
                if expected["cached_prompt_tokens"]
                else None
            ),
        }
        response = {
            "id": request_id,
            "created": 1,
            "model": body["model"],
            "choices": [],
            "usage": usage,
        }
        gate = holds.get(request_id)
        if not body.get("stream"):
            if gate:
                await gate.wait()
            return response

        async def events():
            content = {
                "id": request_id,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "Hello 世界"},
                        "finish_reason": None,
                    }
                ],
            }
            if (body.get("stream_options") or {}).get("continuous_usage_stats"):
                content["usage"] = {
                    "prompt_tokens": expected["prompt_tokens"],
                    "completion_tokens": 1,
                    "total_tokens": expected["prompt_tokens"] + 1,
                }
            raw = ("data: " + json.dumps(content, ensure_ascii=False) + "\r\n\r\n").encode()
            for offset in range(0, len(raw), 3):
                yield raw[offset : offset + 3]
            if gate and request_id not in after_usage:
                await gate.wait()
            if case == "cut":
                return
            # Repeated cumulative usage deliberately must not double-account.
            yield ("data: " + json.dumps(response) + "\n\n").encode()
            yield ("data: " + json.dumps(response) + "\n\n").encode()
            if gate and request_id in after_usage:
                await gate.wait()
            yield b"data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app
