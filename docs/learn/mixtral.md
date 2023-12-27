# Mixtral 8x7B

This example demonstrates how to deploy Mixtral
with `dstack`'s [services](../docs/guides/services.md).

## Define the configuration

To deploy Mixtral as a service, you have to define the corresponding configuration file.
Below are multiple variants: via vLLM (`fp16`), TGI (`fp16`), or TGI (`int4`).

=== "vLLM `fp16`"

    <div editor-title="llms/mixtral/vllm.dstack.yml"> 

    ```yaml
    type: service
    # This configuration deploys Mixtral in fp16 using vLLM
    
    python: "3.11"
    
    commands:
      - pip install vllm
      - python -m vllm.entrypoints.openai.api_server
        --model mistralai/Mixtral-8X7B-Instruct-v0.1
        --host 0.0.0.0
        --tensor-parallel-size 2 # Should match the number of GPUs
    
    port: 8000
    ```

    </div>

=== "TGI `fp16`"

    <div editor-title="llms/mixtral/tgi.dstack.yml"> 

    ```yaml
    type: service
    # This configuration deploys Mixtral in fp16 using TGI
    
    image: ghcr.io/huggingface/text-generation-inference:latest
    
    env:
      - MODEL_ID=mistralai/Mixtral-8x7B-Instruct-v0.1
    
    commands:
      - text-generation-launcher 
        --hostname 0.0.0.0 
        --port 8000 
        --trust-remote-code
        --num-shard 2 # Should match the number of GPUs
    
    port: 8000
    ```

    </div>

=== "TGI `int4`"

    <div editor-title="llms/mixtral/tgi-gptq.dstack.yml"> 

    ```yaml
    type: service
    # This configuration deploys Mixtral in int4 using TGI
    
    image: ghcr.io/huggingface/text-generation-inference:latest
    
    env:
      - MODEL_ID=TheBloke/Mixtral-8x7B-Instruct-v0.1-GPTQ
    
    commands:
      - text-generation-launcher 
        --hostname 0.0.0.0 
        --port 8000 
        --trust-remote-code 
        --quantize gptq
    
    port: 8000
    ```

    </div>

> vLLM's support for quantized Mixtral is not yet stable. 

## Run the configuration

!!! warning "Prerequisites"
    Before running a service, make sure to set up a [gateway](../docs/guides/services.md#set-up-a-gateway).
    However, it's not required when using dstack Cloud, as it's set up automatically.

!!! info "Resources"
    For `fp16`, deployment of Mixtral, ensure a minimum total GPU memory of `100GB` and disk size of `200GB`.
    Also, make sure to adjust the `--tensor-parallel-size` and `--num-shard` parameters in the YAML configuration to align
    with the number of GPUs used.
    For `int4`, request at least `25GB` of GPU memory.

=== "vLLM `fp16`"

    <div class="termy">
    
    ```shell
    $ dstack run . -f llms/mixtral/vllm.dstack.yml --gpu "80GB:2" --disk 200GB
    ```
    
    </div>

=== "TGI `fp16`"

    <div class="termy">
    
    ```shell
    $ dstack run . -f llms/mixtral/tgi.dstack.yml --gpu "80GB:2" --disk 200GB
    ```
    
    </div>

=== "TGI `int4`"

    <div class="termy">
    
    ```shell
    $ dstack run . -f llms/mixtral/tgi-gptq.dstack.yml --gpu 25GB
    ```
    
    </div>

!!! info "Endpoint URL"
    Once the service is deployed, its endpoint will be available at 
    `https://<run-name>.<domain-name>` (using the domain set up for the gateway).

    If you wish to customize the run name, you can use the `-n` argument with the `dstack run` command.

[//]: # (Once the service is up, you can query it via it's OpenAI compatible endpoint:)
[//]: # (<div class="termy">)
[//]: # ()
[//]: # (```shell)
[//]: # ($ curl -X POST --location https://yellow-cat-1.mydomain.com/v1/completions \)
[//]: # (    -H "Content-Type: application/json" \)
[//]: # (    -d '{)
[//]: # (          "model": "mistralai/Mixtral-8X7B-Instruct-v0.1",)
[//]: # (          "prompt": "Hello!",)
[//]: # (          "max_tokens": 25,)
[//]: # (        }')
[//]: # (```)
[//]: # ()
[//]: # (</div>)

[//]: # (!!! info "OpenAI-compatible API")
[//]: # (    Since vLLM provides an OpenAI-compatible endpoint, feel free to access it using various OpenAI-compatible tools like)
[//]: # (    Chat UI, LangChain, Llama Index, etc. )

??? info "Hugging Face Hub token"

    To use a model with gated access, ensure configuring the `HUGGING_FACE_HUB_TOKEN` environment variable 
    (with [`--env`](../docs/reference/cli/index.md#dstack-run) in `dstack run` or 
    using [`env`](../docs/reference/dstack.yml.md#service) in the configuration file).
    
[//]: # (    <div class="termy">)
[//]: # (    )
[//]: # (    ```shell)
[//]: # (    $ dstack run . --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; -f llms/mixtral.dstack.yml --gpu "80GB:2" --disk 200GB)
[//]: # (    ```)
[//]: # (    </div>)

## Source code
    
The complete, ready-to-run code is available in [dstackai/dstack-examples](https://github.com/dstackai/dstack-examples).

## What's next?

1. Check the [vLLM](tgi.md) and [Text Generation Inference](tgi.md) examples
2. Read about [services](../docs/guides/services.md)
3. See all [learning materials](index.md)
4. Join the [Discord server](https://discord.gg/u8SmfwPpMd)