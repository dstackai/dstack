# Deploying LLMs with vLLM

!!! info "NOTE:"
    This example demonstrates how to deploy an LLM
    using [Services](../docs/guides/services.md) and [vLLM](https://vllm.ai/),
    an open-source library.

    If you'd like to deploy an LLM via a simple API,
    consider using the [Text generation](../docs/guides/text-generation.md) API. It's a lot simpler.

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
    If you're using dstack Cloud, the dstack gateway is configured automatically for you.

<div class="termy">

```shell
$ dstack run . -f vllm/serve.dstack.yml --gpu 24GB
```

</div>

!!! info "Endpoint URL"
    Once the service is deployed, its endpoint will be available at 
    `https://<run-name>.<domain-name>` (using the domain set up for the gateway).

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
    (with [`--env`](../docs/reference/cli/index.md#dstack-run) in `dstack run` or 
    using [`env`](../docs/reference/dstack.yml/service.md#env) in the configuration file).
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f vllm/serve.dstack.yml --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; --gpu 24GB
    ```
    </div>

!!! info "Source code"
    The complete, ready-to-run code is available in [dstackai/dstack-examples](https://github.com/dstackai/dstack-examples).