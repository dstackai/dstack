# vLLM

This example demonstrates how to use [vLLM](https://vllm.ai/) with `dstack`'s [services](../docs/concepts/services.md) to deploy LLMs.

## Define the configuration

To deploy an LLM as a service using vLLM, you have to define the following configuration file:

<div editor-title="deployment/vllm/serve.dstack.yml"> 

```yaml
type: service

python: "3.11"
env:
  - MODEL=NousResearch/Llama-2-7b-chat-hf
commands:
  - pip install vllm
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
port: 8000

resources:
  gpu: 24GB

# (Optional) Enable the OpenAI-compatible endpoint
model:
  format: openai
  type: chat
  name: NousResearch/Llama-2-7b-chat-hf
```

</div>

## Run the configuration

!!! warning "Gateway"
    Before running a service, ensure that you have configured a [gateway](../docs/concepts/services.md#set-up-a-gateway).
    If you're using [dstack Sky](https://sky.dstack.ai), the default gateway is configured automatically for you.

<div class="termy">

```shell
$ dstack run . -f deployment/vllm/serve.dstack.yml
```

</div>

## Access the endpoint

Once the service is up, you can query it at 
`https://<run name>.<gateway domain>` (using the domain set up for the gateway):

!!! info "Authentication"
    By default, the service endpoint requires the `Authentication` header with `"Bearer <dstack token>"`.

[//]: # (<div class="termy">)
[//]: # (```shell)
[//]: # ($ curl -X POST --location https://yellow-cat-1.example.com/v1/completions \)
[//]: # (    -H "Content-Type: application/json" \)
[//]: # (    -H 'Authentication: "Bearer &lt;dstack token&gt;"' \)
[//]: # (    -d '{)
[//]: # (          "model": "NousResearch/Llama-2-7b-chat-hf",)
[//]: # (          "prompt": "San Francisco is a",)
[//]: # (          "max_tokens": 7,)
[//]: # (          "temperature": 0)
[//]: # (        }')
[//]: # (```)
[//]: # (</div>)

#### OpenAI interface

Because we've configured the model mapping, it will also be possible 
to access the model at `https://gateway.<gateway domain>` via the OpenAI-compatible interface.

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://gateway.<gateway domain>", 
    api_key="<dstack token>"
)

completion = client.chat.completions.create(
    model="mixtral",
    messages=[
        {
            "role": "user",
            "content": "Compose a poem that explains the concept of recursion in programming.",
        }
    ],
    stream=True,
)

for chunk in completion:
    print(chunk.choices[0].delta.content, end="")
print()
```

!!! info "Hugging Face Hub token"

    To use a model with gated access, ensure configuring the `HUGGING_FACE_HUB_TOKEN` environment variable 
    (with [`--env`](../docs/reference/cli/index.md#dstack-run) in `dstack run` or 
    using [`env`](../docs/reference/dstack.yml.md#service) in the configuration file).
    
[//]: # (    <div class="termy">)
[//]: # (    )
[//]: # (    ```shell)
[//]: # (    $ dstack run . -f vllm/serve.dstack.yml --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; --gpu 24GB)
[//]: # (    ```)
[//]: # (    </div>)

## Source code
    
The complete, ready-to-run code is available in [`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples).

!!! info "What's next?"
    1. Check the [Text Generation Inference](tgi.md) example
    2. Read about [services](../docs/concepts/services.md)
    3. Browse [examples](index.md)
    4. Join the [Discord server](https://discord.gg/u8SmfwPpMd)