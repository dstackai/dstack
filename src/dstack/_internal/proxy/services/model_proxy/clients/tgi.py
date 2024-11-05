import datetime
import json
import uuid
from typing import AsyncIterator, Dict, List

import httpx
import jinja2
import jinja2.sandbox

from dstack._internal.proxy.errors import ProxyError
from dstack._internal.proxy.schemas.model_proxy import (
    ChatCompletionsChoice,
    ChatCompletionsChunk,
    ChatCompletionsChunkChoice,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    ChatCompletionsUsage,
    ChatMessage,
    FinishReason,
)
from dstack._internal.proxy.services.model_proxy.clients import ChatCompletionsClient


class TGIChatCompletions(ChatCompletionsClient):
    # https://huggingface.github.io/text-generation-inference/
    def __init__(self, http_client: httpx.AsyncClient, chat_template: str, eos_token: str):
        self.client = http_client
        self.eos_token = eos_token

        try:
            jinja_env = jinja2.sandbox.ImmutableSandboxedEnvironment(
                trim_blocks=True, lstrip_blocks=True
            )
            jinja_env.globals["raise_exception"] = raise_exception
            self.chat_template = jinja_env.from_string(chat_template)
        except jinja2.TemplateError as e:
            raise ProxyError(f"Failed to compile chat template: {e}")

    async def generate(self, request: ChatCompletionsRequest) -> ChatCompletionsResponse:
        payload = self.get_payload(request)
        resp = await self.client.post("/generate", json=payload)
        if resp.status_code != 200:
            raise ProxyError(resp.text)  # TODO(egor-s)
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
                        raise ProxyError(data["error"])
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
        try:
            inputs = self.chat_template.render(
                messages=request.messages,
                add_generation_prompt=True,
            )
        except jinja2.TemplateError as e:
            raise ProxyError(f"Failed to render chat template: {e}")

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
        raise ProxyError(f"Unknown finish reason: {reason}")

    @staticmethod
    def trim_stop_tokens(text: str, stop_tokens: List[str]) -> str:
        for stop_token in stop_tokens:
            if text.endswith(stop_token):
                return text[: -len(stop_token)]
        return text


def raise_exception(message: str):
    raise jinja2.TemplateError(message)
