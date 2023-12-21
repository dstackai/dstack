# Mixtral

This example demonstrates how to deploy `mistralai/Mixtral-8x7B-Instruct-v0.1 ` 
with `dstack`'s [services](../docs/guides/services.md) and [vLLM](https://vllm.ai/).

## Define the configuration

To deploy Mixtral as a service using vLLM, define the following configuration file:

<div editor-title="llms/mixtral/vllm.dstack.yml"> 

```yaml
type: service

python: "3.11"

commands:
  - conda install cuda # (required by megablocks)
  - pip install torch # (required by megablocks)
  - pip install vllm megablocks
  - python -m vllm.entrypoints.openai.api_server
    --model mistralai/Mixtral-8X7B-Instruct-v0.1
    --host 0.0.0.0
    --tensor-parallel-size 2 # should match the number of GPUs

port: 8000
```

</div>

## Run the configuration

!!! warning "Prerequisites"
    Before running a service, make sure to set up a [gateway](../docs/guides/services.md#set-up-a-gateway).
    However, it's not required when using dstack Cloud, as it's set up automatically.

<div class="termy">

```shell
$ dstack run . -f llms/mixtral.dstack.yml --gpu "80GB:2" --disk 200GB
```

</div>

!!! info "GPU memory"
    To deploy Mixtral in `fp16`, ensure a minimum of `100GB` total GPU memory, 
    and adjust the `--tensor-parallel-size` parameter in the YAML configuration 
    to match the number of GPUs.

!!! info "Disk size"
    To deploy Mixtral, ensure a minimum of `200GB` of disk size.

!!! info "Endpoint URL"
    Once the service is deployed, its endpoint will be available at 
    `https://<run-name>.<domain-name>` (using the domain set up for the gateway).

    If you wish to customize the run name, you can use the `-n` argument with the `dstack run` command.

Once the service is up, you can query it via it's OpenAI compatible endpoint:

<div class="termy">

```shell
$ curl -X POST --location https://yellow-cat-1.mydomain.com/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
          "model": "mistralai/Mixtral-8X7B-Instruct-v0.1",
          "prompt": "Hello!",
          "max_tokens": 25,
        }'
```

</div>

!!! info "OpenAI-compatible API"
    Since vLLM provides an OpenAI-compatible endpoint, feel free to access it using various OpenAI-compatible tools like
    Chat UI, LangChain, Llama Index, etc. 

??? info "Hugging Face Hub token"

    To use a model with gated access, ensure configuring the `HUGGING_FACE_HUB_TOKEN` environment variable 
    (with [`--env`](../docs/reference/cli/index.md#dstack-run) in `dstack run` or 
    using [`env`](../docs/reference/dstack.yml.md#service) in the configuration file).
    
    <div class="termy">
    
    ```shell
    $ dstack run . --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; -f llms/mixtral.dstack.yml --gpu "80GB:2" --disk 200GB
    ```
    </div>

## Source code
    
The complete, ready-to-run code is available in [dstackai/dstack-examples](https://github.com/dstackai/dstack-examples).

## What's next?

1. Check the [vLLM](tgi.md) and [Text Generation Inference](tgi.md) examples
2. Read about [services](../docs/guides/services.md)
3. See all [learning materials](index.md)
4. Join the [Discord server](https://discord.gg/u8SmfwPpMd)