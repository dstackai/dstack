import asyncio
import datetime
import json
import uuid
from typing import AsyncIterator, Dict, List, Optional

import httpx
import jinja2

from dstack.gateway.errors import GatewayError
from dstack.gateway.openai.clients import ChatCompletionsClient
from dstack.gateway.openai.schemas import (
    ChatCompletionsChoice,
    ChatCompletionsChunk,
    ChatCompletionsChunkChoice,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    ChatCompletionsUsage,
    ChatMessage,
    FinishReason,
)


class TGIChatCompletions(ChatCompletionsClient):
    # https://huggingface.github.io/text-generation-inference/
    def __init__(
        self, base_url: str, chat_template: str, eos_token: str, host: Optional[str] = None
    ):
        self.client = AsyncClientWrapper(
            base_url=base_url.rstrip("/"),
            headers={} if host is None else {"Host": host},
            timeout=60,
        )
        self.chat_template = jinja2.Template(chat_template)
        self.eos_token = eos_token

    async def generate(self, request: ChatCompletionsRequest) -> ChatCompletionsResponse:
        payload = self.get_payload(request)
        resp = await self.client.post("/generate", json=payload)
        if resp.status_code != 200:
            raise GatewayError(resp.text)  # TODO(egor-s)
        data = resp.json()

        choices = [
            ChatCompletionsChoice(
                finish_reason=self.finish_reason(data["details"]["finish_reason"]),
                index=0,
                message=ChatMessage(
                    role="assistant",
                    content=self.trim_stop_tokens(
                        data["generated_text"], payload["parameters"]["stop"]
                    ),
                ),
            )
        ]
        completion_tokens = data["details"]["generated_tokens"]
        prompt_tokens = len(data["details"]["prefill"])

        for i, sequence in enumerate(data["details"].get("best_of_sequences", []), start=1):
            choices.append(
                ChatCompletionsChoice(
                    finish_reason=self.finish_reason(sequence["finish_reason"]),
                    index=i,
                    message=ChatMessage(
                        role="assistant",
                        content=self.trim_stop_tokens(
                            sequence["generated_text"], payload["parameters"]["stop"]
                        ),
                    ),
                )
            )
            completion_tokens += sequence["generated_tokens"]

        return ChatCompletionsResponse(
            id=uuid.uuid4().hex,
            choices=choices,
            created=int(datetime.datetime.utcnow().timestamp()),
            model=request.model,
            system_fingerprint=f"fp_{data['details']['seed']}",
            usage=ChatCompletionsUsage(
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,  # TODO(egor-s): do we need to multiply by number of sequences?
                total_tokens=completion_tokens + prompt_tokens,
            ),
        )

    async def stream(self, request: ChatCompletionsRequest) -> AsyncIterator[ChatCompletionsChunk]:
        completion_id = uuid.uuid4().hex
        created = int(datetime.datetime.utcnow().timestamp())

        payload = self.get_payload(request)
        async with self.client.stream("POST", "/generate_stream", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[len("data:") :].strip("\n"))
                    if "error" in data:
                        raise GatewayError(data["error"])
                    chunk = ChatCompletionsChunk(
                        id=completion_id,
                        choices=[],
                        created=created,
                        model=request.model,
                        system_fingerprint="",
                    )
                    if data["details"] is not None:
                        chunk.choices = [
                            ChatCompletionsChunkChoice(
                                delta={},
                                logprobs=None,
                                finish_reason=self.finish_reason(data["details"]["finish_reason"]),
                                index=0,
                            )
                        ]
                    else:
                        chunk.choices = [
                            ChatCompletionsChunkChoice(
                                delta={"content": data["token"]["text"], "role": "assistant"},
                                logprobs=None,
                                finish_reason=None,
                                index=0,
                            )
                        ]
                    yield chunk

    def get_payload(self, request: ChatCompletionsRequest) -> Dict:
        inputs = self.chat_template.render(
            messages=request.messages,
            add_generation_prompt=True,
        )
        stop = ([request.stop] if isinstance(request.stop, str) else request.stop) or []
        if self.eos_token not in stop:
            stop.append(self.eos_token)

        parameters = {
            "do_sample": True,  # activate logits sampling
            "max_new_tokens": request.max_tokens,
            # TODO(egor-s): OpenAI parameters do not convert to `repetition_penalty`
            # "repetition_penalty": None,
            # "return_full_text": False,
            "stop": stop,
            "seed": request.seed,
            "temperature": request.temperature,
            # OpenAI doesn't specify `top_k` parameter
            # "top_k": None,
            # "truncate": None,
            # "typical_p": None,
            "best_of": request.n,
            # "watermark": False,
            "details": True,  # to get best_of_sequences
            "decoder_input_details": not request.stream,
        }
        if request.top_p < 1.0:
            parameters["top_p"] = request.top_p
        return {
            "inputs": inputs,
            "parameters": parameters,
        }

    @staticmethod
    def finish_reason(reason: str) -> FinishReason:
        if reason == "stop_sequence" or reason == "eos_token":
            return "stop"
        if reason == "length":
            return "length"
        raise ValueError(f"Unknown finish reason: {reason}")

    @staticmethod
    def trim_stop_tokens(text: str, stop_tokens: List[str]) -> str:
        for stop_token in stop_tokens:
            if text.endswith(stop_token):
                return text[: -len(stop_token)]
        return text


class AsyncClientWrapper(httpx.AsyncClient):
    def __del__(self):
        try:
            asyncio.get_running_loop().create_task(self.aclose())
        except Exception:
            pass
