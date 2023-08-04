# Serving LLMs with vLLM

Serving LLMs can be slow, even on expensive hardware. This example demonstrates how to utilize the 
[`vllm`](https://vllm.ai/) library to serve LLMs with optimized performance.

## What is vLLM?

`vllm` is an open-source library that significantly increases LLM throughput, thanks to the optimized memory-sharing
algorithm called PageAttention.

The library also offers other benefits such as continuous batching, 
GPU parallelism, streaming output, OpenAI-compatibility, and more.

To try `vllm` with `dstack`, follow the instructions below.

## Prerequisites

!!! info "NOTE:"
    Before using `dstack` with a particular cloud, make sure to [configure](../docs/guides/projects.md) the corresponding project.

Each LLM model requires specific resources. To inform `dstack` about the required resources, you need to 
[define](../docs/reference/profiles.yml.md) a profile via the `.dstack/profiles.yaml` file within your project.

Below is a profile that will provision a cloud instance with `24GB` of memory and a `T4` GPU in the `gcp` project.

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: gcp-t4
    project: gcp
    resources:
      memory: 24GB
      gpu:
        name: T4
    default: true
```

</div>

## Running an endpoint

Here's the configuration that runs an LLM as an OpenAI-compatible endpoint:

<div editor-title="vllm/serve.dstack.yml"> 

```yaml
type: task

env:
  # (Required) Specify the name of the model
  - MODEL=facebook/opt-125m
  # (Optional) Specify your Hugging Face token
  - HUGGING_FACE_HUB_TOKEN=

ports:
  - 8000

commands:
  - conda install cuda # Required since vLLM will rebuild the CUDA kernel
  - pip install vllm # Takes 5-10 minutes
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
```

</div>

Here's how you run it with `dstack`:

<div class="termy">

```shell
$ dstack run . -f vllm/serve.dstack.yml --ports 8000:8000
```

</div>

`dstack` will provision the cloud instance, run the task, and forward the defined ports to your local
machine for secure and convenient access.

Now, you can query the endpoint in the same format as OpenAI API:

<div class="termy">

```shell
$ curl -X POST --location http://127.0.0.1:8000/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
          "model": "facebook/opt-125m",
          "prompt": "San Francisco is a",
          "max_tokens": 7,
          "temperature": 0
        }'
```

</div>

For more details on how `vllm` works, check their [documentation](https://vllm.readthedocs.io/).

[Source code](https://github.com/dstackai/dstack-examples){ .md-button .md-button--github }

## Limitations

To use `vllm` with `dstack`, be aware of the following limitations:

1. The `vllm` library currently supports a [limited set](https://vllm.readthedocs.io/en/latest/models/supported_models.html) of LLMs, but Llama 2 is supported.
2. The `vllm` library lacks quantization support. Check the progress [here](https://github.com/vllm-project/vllm/issues/316).