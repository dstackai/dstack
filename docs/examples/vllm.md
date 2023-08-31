# Serving LLMs with vLLM

Serving LLMs can be slow. The example below demonstrates how to use the 
[`vllm`](https://vllm.ai/) library to serve LLMs with optimized performance.

## What is vLLM?

`vllm` is an open-source library that significantly increases LLM throughput, thanks to the optimized memory-sharing
algorithm called PageAttention.

The library also offers other benefits such as continuous batching, 
GPU parallelism, streaming output, OpenAI-compatibility, and more.

To try `vllm` with `dstack`, follow the instructions below.

## Define the configuration

??? info "Tasks"
    If you want to serve an application for development purposes only, you can use 
    [tasks](../docs/guides/services.md). 
    In this scenario, while the application runs in the cloud, 
    it is accessible from your local machine only.

For production purposes, the optimal approach to serve an application is by using 
[services](../docs/guides/services.md). In this case, the application can be accessed through a public endpoint.

Here's the configuration that uses services to run an LLM as an OpenAI-compatible endpoint:

<div editor-title="vllm/serve.dstack.yml"> 

```yaml
type: service

python: "3.11"

env:
  - MODEL=NousResearch/Llama-2-7b-hf

port: 8000

commands:
  - pip install vllm
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
```

</div>

## Run the configuration

!!! warning "NOTE:"
    Before running a service, ensure that you have configured a [gateway](../docs/guides/clouds.md#configuring-gateways).

<div class="termy">

```shell
$ dstack run . -f vllm/serve.dstack.yml --gpu 24GB
```

</div>

!!! info "Endpoint URL"
    If you've configured a [wildcard domain](clouds.md#configuring-gateways) for the gateway, 
    `dstack` enables HTTPS automatically and serves the service at 
    `https://<run name>.<your domain name>`.

    If you wish to customize the run name, you can use the `-n` argument with the `dstack run` command.

Once the service is up, you can query the endpoint:

<div class="termy">

```shell
$ curl -X POST --location https://yellow-cat-1.mydomain.com/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
          "model": "NousResearch/Llama-2-7b-hf",
          "prompt": "San Francisco is a",
          "max_tokens": 7,
          "temperature": 0
        }'
```

</div>

### Gated models

To use a gated-access model from Hugging Face Hub, make sure to set up either the `HUGGING_FACE_HUB_TOKEN` secret
(using [`dstack secrets`](../docs/reference/cli/secrets.md#dstack-secrets-add)),
or environment variable (with [`--env`](../docs/reference/cli/run.md#ENV) in `dstack run` or 
using [`env`](../docs/reference/dstack.yml/service.md#env) in the configuration file).

<div class="termy">

```shell
$ dstack run . -f vllm/serve.dstack.yml --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; --gpu 24GB
```
</div>

[Source code](https://github.com/dstackai/dstack-examples){ .md-button .md-button--github }