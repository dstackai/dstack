---
title: DeepSeek V4
description: Deploying DeepSeek-V4-Pro using SGLang on NVIDIA B200:8
---

# DeepSeek V4

This example shows how to deploy `deepseek-ai/DeepSeek-V4-Pro` as a
[service](https://dstack.ai/docs/services) using
[SGLang](https://github.com/sgl-project/sglang) and `dstack`.

## Apply a configuration

Save the following configuration as `deepseek-v4.dstack.yml`.

<div editor-title="deepseek-v4.dstack.yml">

```yaml
type: service
name: deepseek-v4

image: lmsysorg/sglang:deepseek-v4-blackwell

env:
  - HF_TOKEN
  - SGLANG_DEEPEP_NUM_MAX_DISPATCH_TOKENS_PER_RANK=256
  - SGLANG_JIT_DEEPGEMM_PRECOMPILE=0

commands:
  - |
    sglang serve \
      --trust-remote-code \
      --model-path deepseek-ai/DeepSeek-V4-Pro \
      --tp 8 \
      --dp 8 \
      --enable-dp-attention \
      --moe-a2a-backend deepep \
      --mem-fraction-static 0.82 \
      --cuda-graph-max-bs 64 \
      --max-running-requests 256 \
      --deepep-config '{"normal_dispatch":{"num_sms":96},"normal_combine":{"num_sms":96}}' \
      --tool-call-parser deepseekv4 \
      --reasoning-parser deepseek-v4 \
      --host 0.0.0.0 \
      --port 30000

port: 30000
model: deepseek-ai/DeepSeek-V4-Pro

volumes:
  - instance_path: /root/.cache
    path: /root/.cache
    optional: true

resources:
  gpu: B200:8
  shm_size: 32GB
  disk: 2TB..
```

</div>

This configuration uses the single-node Blackwell `DeepSeek-V4-Pro` recipe
shape for `8 x NVIDIA B200`.

Export your Hugging Face token and apply the configuration with
[`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md).

<div class="termy">

```shell
$ export HF_TOKEN=<your-hf-token>
$ dstack apply -f deepseek-v4.dstack.yml
```

</div>

If no gateway is created, the service endpoint will be available at
`<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/services/main/deepseek-v4/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "deepseek-ai/DeepSeek-V4-Pro",
      "messages": [
        {
          "role": "user",
          "content": "What is 15% of 240? Reply with just the number."
        }
      ],
      "temperature": 0,
      "max_tokens": 32
    }'
```

</div>

## Reasoning mode

To separate the model's reasoning into `reasoning_content`, keep
`--reasoning-parser deepseek-v4` in the server command and send
`chat_template_kwargs` in the request body.

For raw HTTP requests, `chat_template_kwargs` and `separate_reasoning` must be
top-level JSON fields.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/services/main/deepseek-v4/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "deepseek-ai/DeepSeek-V4-Pro",
      "messages": [
        {
          "role": "user",
          "content": "Solve step by step: If 3x + 5 = 20, what is x?"
        }
      ],
      "temperature": 0,
      "max_tokens": 256,
      "chat_template_kwargs": {
        "thinking": true
      },
      "separate_reasoning": true
    }'
```

</div>

This returns both:

- `reasoning_content`: a separate reasoning trace
- `content`: the final user-visible answer

## Deployment notes

- The first startup can take several minutes while the model loads and SGLang
  finishes initialization.
- The optional `/root/.cache` instance volume helps reuse the model cache on
  backends that support instance volumes.

## What's next?

1. Read the [DeepSeek-V4-Pro model card](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro)
2. Read the [DeepSeek-V4 SGLang cookbook](https://docs.sglang.io/cookbook/autoregressive/DeepSeek/DeepSeek-V4)
3. Browse the dedicated [SGLang](https://dstack.ai/examples/inference/sglang/) and [vLLM](https://dstack.ai/examples/inference/vllm/) examples
