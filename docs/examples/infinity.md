# Infinity

This example demonstrates how to use [Infinity](https://github.com/michaelfeil/infinity) with `dstack`'
s [services](../docs/concepts/services.md) to deploy
any [SentenceTransformers](https://github.com/UKPLab/sentence-transformers/) based embedding models.

## Define the configuration

To deploy a `SentenceTransformers` based embedding models using `Infinity`, you need to define the following configuration file at minimum:

<div editor-title="deployment/infinity/serve.dstack.yml"> 

```yaml
type: service

image: michaelf34/infinity:latest
env:
  - MODEL_ID=BAAI/bge-small-en-v1.5
commands:
  - infinity_emb --model-name-or-path $MODEL_ID --port 80
port: 80

resources:
  gpu: 16GB
```

</div>

## Run the configuration

!!! warning "Gateway"
    Before running a service, ensure that you have configured a [gateway](../docs/concepts/services.md#set-up-a-gateway).
    If you're using dstack Cloud, the default gateway is configured automatically for you.

<div class="termy">

```shell
$ dstack run . -f infinity/serve.dstack.yml
```

</div>

## Access the endpoint
    
Once the service is up, you can query it at 
`https://<run name>.<gateway domain>` (using the domain set up for the gateway):

!!! info "Authentication"
    By default, the service endpoint requires the `Authentication` header with `"Bearer <dstack token>"`.

### OpenAI interface

Any embedding models served by Infinity automatically comes with [OpenAI's Embeddings APIs](https://platform.openai.com/docs/guides/embeddings) compatible APIs, 
so we can directly use `openai` package to interact with the deployed Infinity.

```python
from openai import OpenAI
from functools import partial

client = OpenAI(base_url="https://<run name>.<gateway domain>", api_key="<dstack token>")

client.embeddings.create = partial(
  client.embeddings.create, model="bge-small-en-v1.5"
)

print(client.embeddings.create(input=["A sentence to encode."]))
```

## Source code
    
The complete, ready-to-run code is available in [`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples).

## What's next?

1. Check the [Text Embeddings Inference](tei.md), [TGI](tgi.md), and [vLLM](vllm.md) examples
2. Read about [services](../docs/concepts/services.md)
3. Browse all [examples](index.md)
4. Join the [Discord server](https://discord.gg/u8SmfwPpMd)