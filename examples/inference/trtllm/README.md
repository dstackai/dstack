---
title: TensorRT-LLM
description: Deploying Qwen3-235B-A22B-FP8 using NVIDIA TensorRT-LLM on NVIDIA GPUs
---

# TensorRT-LLM

This example shows how to deploy `nvidia/Qwen3-235B-A22B-FP8` using
[TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM) and `dstack`.

## Apply a configuration

Here's an example of a service that deploys
`nvidia/Qwen3-235B-A22B-FP8` using TensorRT-LLM.

<div editor-title="qwen235.dstack.yml">

```yaml
type: service
name: qwen235

image: nvcr.io/nvidia/tensorrt-llm/release:1.3.0rc11

env:
  - HF_HUB_ENABLE_HF_TRANSFER=1

commands:
  - pip install hf_transfer
  - |
    trtllm-serve serve nvidia/Qwen3-235B-A22B-FP8 \
      --host 0.0.0.0 \
      --port 8000 \
      --backend pytorch \
      --tp_size $DSTACK_GPUS_NUM \
      --max_batch_size 32 \
      --max_num_tokens 4096 \
      --kv_cache_free_gpu_memory_fraction 0.75

port: 8000
model: nvidia/Qwen3-235B-A22B-FP8

volumes:
  - instance_path: /root/.cache
    path: /root/.cache
    optional: true

resources:
  cpu: 96..
  memory: 512GB..
  shm_size: 32GB
  disk: 1000GB..
  gpu: H100:8
```
</div>

Apply it with [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ dstack apply -f qwen235.dstack.yml
```

</div>

## Access the endpoint

If no gateway is created, the service endpoint will be available at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
$ curl http://127.0.0.1:3000/proxy/services/main/qwen235/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "nvidia/Qwen3-235B-A22B-FP8",
      "messages": [
        {
          "role": "user",
          "content": "A bat and a ball cost $1.10 total. The bat costs $1.00 more than the ball. How much does the ball cost?"
        }
      ],
      "chat_template_kwargs": {"enable_thinking": true},
      "max_tokens": 1024,
      "temperature": 0.0
    }'
```

</div>

When a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured, the service endpoint will be available at `https://qwen235.<gateway domain>/`.

## What's next?

1. Read about [services](https://dstack.ai/docs/concepts/services) and [gateways](https://dstack.ai/docs/concepts/gateways)
2. Browse the [TensorRT-LLM deployment guides](https://nvidia.github.io/TensorRT-LLM/deployment-guide/index.html) and the [Qwen3 deployment guide](https://nvidia.github.io/TensorRT-LLM/deployment-guide/deployment-guide-for-qwen3-on-trtllm.html)
3. See the [`trtllm-serve` reference](https://nvidia.github.io/TensorRT-LLM/commands/trtllm-serve/trtllm-serve.html)
