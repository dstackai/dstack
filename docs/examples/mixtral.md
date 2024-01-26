# Mixtral 8x7B

This example demonstrates how to deploy Mixtral
with `dstack`'s [services](../docs/concepts/services.md).

## Define the configuration

To deploy Mixtral as a service, you have to define the corresponding configuration file.
Below are multiple variants: via vLLM (`fp16`), TGI (`fp16`), or TGI (`int4`).

=== "TGI `fp16`"

    <div editor-title="llms/mixtral/tgi.dstack.yml"> 

    ```yaml
    type: service
    
    image: ghcr.io/huggingface/text-generation-inference:latest
    env:
      - MODEL_ID=mistralai/Mixtral-8x7B-Instruct-v0.1
    commands:
      - text-generation-launcher 
        --port 80
        --trust-remote-code
        --num-shard 2 # Should match the number of GPUs 
    port: 80

    # Optional mapping for OpenAI-compatible endpoint
    model:
      type: chat
      name: TheBloke/Mixtral-8x7B-Instruct-v0.1-GPTQ
      format: tgi
    ```

    </div>

=== "TGI `int4`"

    <div editor-title="llms/mixtral/tgi-gptq.dstack.yml"> 

    ```yaml
    type: service

    image: ghcr.io/huggingface/text-generation-inference:latest 
    env:
      - MODEL_ID=TheBloke/Mixtral-8x7B-Instruct-v0.1-GPTQ 
    commands:
      - text-generation-launcher
        --port 80
        --trust-remote-code
        --quantize gptq
    port: 80

    # Optional mapping for OpenAI-compatible endpoint
    model:
      type: chat
      name: TheBloke/Mixtral-8x7B-Instruct-v0.1-GPTQ
      format: tgi
    ```

    </div>

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

    !!! info "NOTE:"
        The [model mapping](../docs/concepts/services.md#model-mapping) to access the model via the 
        gateway's OpenAI-compatible endpoint is not yet supported for vLLM.

        Also, support for quantized Mixtral in vLLM is not yet stable.

## Run the configuration

!!! warning "Prerequisites"
    Before running a service, make sure to set up a [gateway](../docs/concepts/services.md#set-up-a-gateway).
    However, it's not required when using dstack Cloud, as it's set up automatically.

For `fp16`, deployment of Mixtral, ensure a minimum total GPU memory of `100GB` and disk size of `200GB`.
For `int4`, request at least `25GB` of GPU memory.

[//]: # (    Also, make sure to adjust the `--tensor-parallel-size` and `--num-shard` parameters in the YAML configuration to align)
[//]: # (    with the number of GPUs used.)
    

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

=== "vLLM `fp16`"

    <div class="termy">
    
    ```shell
    $ dstack run . -f llms/mixtral/vllm.dstack.yml --gpu "80GB:2" --disk 200GB
    ```
    
    </div>

## Access the endpoint

Once the service is up, you'll be able to access it at `https://<run name>.<gateway domain>`.

#### OpenAI interface

In case the service has the [model mapping](../docs/concepts/services.md#model-mapping) configured, you will also be able 
to access the model at `https://gateway.<gateway domain>` via the OpenAI-compatible interface.

```python
from openai import OpenAI


client = OpenAI(
  base_url="https://gateway.example.com",
  api_key="none"
)

completion = client.chat.completions.create(
  model="mistralai/Mixtral-8x7B-Instruct-v0.1",
  messages=[
    {"role": "user", "content": "Compose a poem that explains the concept of recursion in programming."}
  ]
)

print(completion.choices[0].message)
```

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
    
The complete, ready-to-run code is available in [`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples).

## What's next?

1. Check the [Text Generation Inference](tgi.md) and [vLLM](vllm.md) examples
2. Read about [services](../docs/concepts/services.md)
3. Browse [examples](index.md)
4. Join the [Discord server](https://discord.gg/u8SmfwPpMd)