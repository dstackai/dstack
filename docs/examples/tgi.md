# Text Generation Inference

This example demonstrates how to use [TGI](https://github.com/huggingface/text-generation-inference) with `dstack`'s [services](../docs/concepts/services.md) to deploy LLMs.

## Define the configuration

To deploy an LLM as a service using TGI, you have to define the following configuration file:

<div editor-title="text-generation-inference/serve.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.1
port: 80
commands:
  - text-generation-launcher --port 80 --trust-remote-code
  
# Optional mapping for OpenAI interface
model:
  type: chat
  name: mistralai/Mistral-7B-Instruct-v0.1
  format: tgi
```

</div>

!!! info "Model mapping"
    Note the `model` property is optional and is only required
    if you're running a chat model and want to access it via an OpenAI-compatible endpoint.
    For more details on how to use it feature, check the documentation on [services](../docs/concepts/services.md).

## Run the configuration

!!! warning "Gateway"
    Before running a service, ensure that you have configured a [gateway](../docs/concepts/services.md#set-up-a-gateway).
    If you're using dstack Cloud, the default gateway is configured automatically for you.

<div class="termy">

```shell
$ dstack run . -f text-generation-inference/serve.dstack.yml --gpu 24GB
```

</div>

### Access the endpoint

Once the service is up, you'll be able to 
access it at `https://<run name>.<gateway domain>`.

<div class="termy">

```shell
$ curl https://yellow-cat-1.example.com/generate \
    -X POST \
    -d '{"inputs":"&lt;s&gt;[INST] What is your favourite condiment?[/INST]"}' \
    -H 'Content-Type: application/json'
```

</div>

#### OpenAI interface

Because we've configured the model mapping, it will also be possible 
to access the model at `https://gateway.<gateway domain>` via the OpenAI-compatible interface.

```python
from openai import OpenAI


client = OpenAI(
  base_url="https://gateway.example.com",
  api_key="none"
)

completion = client.chat.completions.create(
  model="mistralai/Mistral-7B-Instruct-v0.1",
  messages=[
    {"role": "user", "content": "Compose a poem that explains the concept of recursion in programming."}
  ]
)

print(completion.choices[0].message)
```

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

## Quantization

Here's an example of using TGI with quantization:

<div editor-title="text-generation-inference/serve.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - MODEL_ID=TheBloke/Llama-2-13B-chat-GPTQ
port: 80
commands:
  - text-generation-launcher --port 80 --trust-remote-code --quantize gptq

model:
  type: chat
  name: TheBloke/Llama-2-13B-chat-GPTQ
  format: tgi
  chat_template: "{% if messages[0]['role'] == 'system' %}{% set loop_messages = messages[1:] %}{% set system_message = messages[0]['content'] %}{% else %}{% set loop_messages = messages %}{% set system_message = false %}{% endif %}{% for message in loop_messages %}{% if (message['role'] == 'user') != (loop.index0 % 2 == 0) %}{{ raise_exception('Conversation roles must alternate user/assistant/user/assistant/...') }}{% endif %}{% if loop.index0 == 0 and system_message != false %}{% set content = '<<SYS>>\\n' + system_message + '\\n<</SYS>>\\n\\n' + message['content'] %}{% else %}{% set content = message['content'] %}{% endif %}{% if message['role'] == 'user' %}{{ '<s>[INST] ' + content.strip() + ' [/INST]' }}{% elif message['role'] == 'assistant' %}{{ ' '  + content.strip() + ' </s>' }}{% endif %}{% endfor %}"
  eos_token: "</s>"
```

</div>

## Source code
    
The complete, ready-to-run code is available in [`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples).

## What's next?

1. Check the [Text Embeddings Inference](tei.md) and [vLLM](vllm.md) examples
2. Read about [services](../docs/concepts/services.md)
3. Browse all [examples](index.md)
4. Join the [Discord server](https://discord.gg/u8SmfwPpMd)