# Text Generation Inference

This example demonstrates how to deploy an LLM using [TGI](https://github.com/huggingface/text-generation-inference), an open-source framework by Hugging Face.

## Define the configuration

To deploy an LLM as a service using TGI, you have to define the following configuration file:

<div editor-title="text-generation-inference/serve.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest

env:
  - MODEL_ID=NousResearch/Llama-2-7b-hf

port: 8000

commands: 
  - text-generation-launcher --hostname 0.0.0.0 --port 8000 --trust-remote-code
```

</div>

## Run the configuration

!!! warning "Gateway"
    Before running a service, ensure that you have configured a [gateway](../docs/guides/services.md#set-up-a-gateway).
    If you're using dstack Cloud, the default gateway is configured automatically for you.

<div class="termy">

```shell
$ dstack run . -f text-generation-inference/serve.dstack.yml --gpu 24GB
```

</div>

!!! info "Endpoint URL"
    Once the service is deployed, its endpoint will be available at 
    `https://<run-name>.<domain-name>` (using the domain set up for the gateway).

    If you wish to customize the run name, you can use the `-n` argument with the `dstack run` command.

Once the service is up, you can query it:

<div class="termy">

```shell
$ curl -X POST --location https://yellow-cat-1.mydomain.com/generate \
    -H 'Content-Type: application/json' \
    -d '{
          "inputs": "What is Deep Learning?",
          "parameters": {
            "max_new_tokens": 20
          }
        }'
```

</div>

!!! info "Hugging Face Hub token"

    To use a model with gated access, ensure configuring the `HUGGING_FACE_HUB_TOKEN` environment variable 
    (with [`--env`](../docs/reference/cli/index.md#dstack-run) in `dstack run` or 
    using [`env`](../docs/reference/dstack.yml.md#service) in the configuration file).
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f text-generation-inference/serve.dstack.yml \
        --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; \
        --gpu 24GB
    ```
    </div>

### Quantization

An LLM typically requires twice the GPU memory compared to its parameter count. For instance, a model with `13B` parameters
needs around `26GB` of GPU memory. To decrease memory usage and fit the model on a smaller GPU, consider using
quantization, which TGI offers as `bitsandbytes` and `gptq` methods. 

Here's an example of the Llama 2 13B model tailored for a `24GB` GPU (A10 or L4):

<div editor-title="text-generation-inference/serve.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest

env:
  - MODEL_ID=TheBloke/Llama-2-13B-GPTQ

port: 8000

commands: 
  - text-generation-launcher --hostname 0.0.0.0 --port 8000 --trust-remote-code --quantize gptq
```

</div>

A similar approach allows running the Llama 2 70B model on an `40GB` GPU (A100).

To calculate the exact GPU memory required for a specific model with different quantization methods, you can use the
[hf-accelerate/memory-model-usage](https://huggingface.co/spaces/hf-accelerate/model-memory-usage) Space.

## Source code
    
The complete, ready-to-run code is available in [dstackai/dstack-examples](https://github.com/dstackai/dstack-examples).

## What's next?

1. Check the [Text Embeddings Inference](tei.md) and [vLLM](vllm.md) examples
2. Read about [services](../docs/guides/services.md)
3. See all [learning materials](index.md)
4. Join the [Discord server](https://discord.gg/u8SmfwPpMd)