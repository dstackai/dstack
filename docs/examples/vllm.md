# Deploying LLMs using vLLM

The example below demonstrates how to use `dstack` to deploy an LLM as a service using vLLM. 

??? info "About services"
    [Services](../docs/guides/services.md) allow running web-based applications as public endpoints. This is the recommended way to deploy LLMs for
    production purposes. If you want to run web applications for development purposes, you can also consider running them as [tasks](../docs/guides/tasks.md).

??? info "About vLLM"
    [vLLM](https://vllm.ai/) is an open-source library for serving LLMs that increases throughput, supports continuous batching, 
    GPU parallelism, streaming output, OpenAI-compatibility, and more.

## Define the configuration

To deploy an LLM as a service using vLLM, you have to define the following configuration file:

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

!!! warning "Gateway"
    Before running a service, ensure that you have configured a [gateway](../docs/guides/services.md#set-up-a-gateway).

<div class="termy">

```shell
$ dstack run . -f vllm/serve.dstack.yml --gpu 24GB
```

</div>

!!! info "Wildcard domain"
    If you've configured a [wildcard domain](../docs/guides/services.md#set-up-a-gateway) for the gateway, 
    `dstack` enables HTTPS automatically and serves the service at 
    `https://<run name>.<your domain name>`.

    If you wish to customize the run name, you can use the `-n` argument with the `dstack run` command.

Once the service is up, you can query it:

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

!!! info "Hugging Face Hub token"

    To use a model with gated access, ensure configuring the `HUGGING_FACE_HUB_TOKEN` environment variable 
    (with [`--env`](../docs/reference/cli/run.md#ENV) in `dstack run` or 
    using [`env`](../docs/reference/dstack.yml/service.md#env) in the configuration file).
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f vllm/serve.dstack.yml --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; --gpu 24GB
    ```
    </div>

!!! info "Source code"
    The complete, ready-to-run code is available in [dstackai/dstack-examples](https://github.com/dstackai/dstack-examples).