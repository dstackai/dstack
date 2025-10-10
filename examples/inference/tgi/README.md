---
title: HuggingFace TGI
description: "This example shows how to deploy Llama 4 Scout to any cloud or on-premises environment using HuggingFace TGI and dstack."
---

# HuggingFace TGI

This example shows how to deploy Llama 4 Scout with `dstack` using [HuggingFace TGI :material-arrow-top-right-thin:{ .external }](https://huggingface.co/docs/text-generation-inference/en/index){:target="_blank"}.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo with examples.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    ```
 
    </div>

## Deployment

Here's an example of a service that deploys [`Llama-4-Scout-17B-16E-Instruct` :material-arrow-top-right-thin:{ .external }](https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E-Instruct){:target="_blank"} using TGI.

<div editor-title="examples/inference/tgi/.dstack.yml">

```yaml
type: service
name: llama4-scout

image: ghcr.io/huggingface/text-generation-inference:latest

env:
  - HF_TOKEN
  - MODEL_ID=meta-llama/Llama-4-Scout-17B-16E-Instruct
  - MAX_INPUT_LENGTH=8192
  - MAX_TOTAL_TOKENS=16384
  # max_batch_prefill_tokens must be >= max_input_tokens
  - MAX_BATCH_PREFILL_TOKENS=8192
commands:
   # Activate the virtual environment at /usr/src/.venv/
   # as required by TGI's latest image.
   - . /usr/src/.venv/bin/activate
   - NUM_SHARD=$DSTACK_GPUS_NUM text-generation-launcher

port: 80
# Register the model
model: meta-llama/Llama-4-Scout-17B-16E-Instruct

# Uncomment to leverage spot instances
#spot_policy: auto

# Uncomment to cache downloaded models
#volumes:
#  - /data:/data

resources:
  gpu: H200:2
  disk: 500GB..
```
</div>

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f examples/inference/tgi/.dstack.yml

 #  BACKEND  REGION     RESOURCES                      SPOT PRICE
 1  vastai   is-iceland 48xCPU, 128GB, 2xH200 (140GB)  no   $7.87
 2  runpod   EU-SE-1    40xCPU, 128GB, 2xH200 (140GB)  no   $7.98

Submit the run llama4-scout? [y/n]: y

Provisioning...
---> 100%
```
</div>

If no gateway is created, the model will be available via the OpenAI-compatible endpoint
at `<dstack server URL>/proxy/models/<project name>/`.

<div class="termy">

```shell
$ curl http://127.0.0.1:3000/proxy/models/main/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
      "messages": [
        {
          "role": "system",
          "content": "You are a helpful assistant."
        },
        {
          "role": "user",
          "content": "What is Deep Learning?"
        }
      ],
      "max_tokens": 128
    }'
```

</div>

When a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured, the OpenAI-compatible endpoint
is available at `https://gateway.<gateway domain>/`.

## Source code

The source-code of this example can be found in
[`examples/inference/tgi` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/inference/tgi).

## What's next?

1. Check [services](https://dstack.ai/docs/services)
2. Browse the [Llama](https://dstack.ai/examples/llms/llama/), [vLLM](https://dstack.ai/examples/inference/vllm/), [SgLang](https://dstack.ai/examples/inference/sglang/) and [NIM](https://dstack.ai/examples/inference/nim/) examples
3. See also [AMD](https://dstack.ai/examples/accelerators/amd/) and
   [TPU](https://dstack.ai/examples/accelerators/tpu/)
