# NIM

NVIDIA Inference Microservice (NIM) simplifies and secures the deployment of foundation models for enterprise applications. It offers production-ready microservices with ongoing security updates, stable APIs, and enterprise support. This allows more developers to utilize AI, bridging the gap between AI development and operational needs. Sources and related content

This document shows how to deploy open-weight large language models with NIM on dstack. This document is written based on the NVIDIA's official document of ['Get Started With NIM'](https://docs.nvidia.com/nim/large-language-models/latest/getting-started.html).

## Instructions

### Prerequisites

To use NIM, you first need to create an account of NGC(NVIDIA GPU Cloud) and a personal key. This personal key will be used for logging into NGC to download target docker images. To do this, follow the [instructions from the NVIDIA's official document](https://docs.nvidia.com/nim/large-language-models/latest/getting-started.html#id1).

### Find a target NIM

Not all open-weight LLMs could be served with NIM, so check out the list of available models from the [NGC Catalog](https://catalog.ngc.nvidia.com/containers?filters=nvidia_nim%7CNVIDIA+NIM%7Cnimmcro_nvidia_nim). 

This tutorial uses [`meta/llama3-8b-instruct`](https://catalog.ngc.nvidia.com/orgs/nim/teams/meta/containers/llama3-8b-instruct). NIM is basically a docker image that wraps the optimized version of the target model with other engines such as TensorRT and TensorRT-LLM. Hence, you need to find dokcer image tag of the target model, and that information is listed on NGC catalog. For instance, `nvcr.io/nim/meta/llama3-8b-instruct:latest` is the docker image tag of Meta AI's LLaMA3 8B Instruct model.

### Serving LLM with NIM

Below shows an example of `service.dstack.yml` to serve an LLM within LLM on dstack. There are two fields to note:

- `image`: specify the docker image tag that you found from the previous step. NIM docker image has its own `ENTRYPOINT`, hence you don't need to specify `commands` field. With only `image` field, the serving will get started and run.

- `registry_auth`: NIM docker image can be downloaded from `nvcr.io` docker image registry only by users with valid credentials(the personal key that you generated from NGC). `registry_auth` acts as the same as `docker login`, hence you need to specify the `username` and `password` as described from [NVIDIA's official document](https://org.ngc.nvidia.com/setup/personal-keys).

```yaml
type: service

image: nvcr.io/nim/meta/llama3-8b-instruct:latest

env:
  - NGC_API_KEY
registry_auth:
  username: $oauthtoken
  password: ${{ env.NGC_API_KEY }}

port: 8000

spot_policy: auto

resources:
  gpu: 48GB

backends: ["aws", "azure", "cudo", "datacrunch", "gcp", "lambda", "oci", "tensordock"]
```
2
??? info "Supported Backends"
    Currently, running NIM is supported on every backends except RunPod and Vast.ai.

Then, as usual, just apply the `service.dstack.yml`.

```shell
$ dstack apply -f service.dstack.yml
```

### Interacting with NIM

After waiting for it to be fully provisioned, you will see the log message similar to the following. `https://ancient-swan-1.deep-diver-main.sky.dstack.ai` is the base endpoint of the service that you can interact with:

```shell
ancient-swan-1 provisioning completed (running)
Service is published at https://ancient-swan-1.deep-diver-main.sky.dstack.ai
```

NIM opens up the endpoints that are compatible to OpenAI APIs. For example, `v1/models` can be used to list models being servied, and `v1/chat/completions` can be used to generate tokens in the form of conversation.

Below shows how generate tokens with `curl` command:

```shell
$ curl -X 'POST' \
  'https://ancient-swan-1.deep-diver-main.sky.dstack.ai/v1/chat/completions' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <YOUR-DSTACK-TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "meta/llama3-8b-instruct",
    "messages": [
      {
        "role":"user",
        "content":"Hello! How are you?"
      }
    ],
    "max_tokens": 2048,
  }'
```

and the same thing can be achieved with OpenAI's Python SDK:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://ancient-swan-1.deep-diver-main.sky.dstack.ai/v1", 
    api_key=<YOUR-DSTACK-TOKEN>
)

response = client.chat.completions.create(
    model="meta/llama3-8b-instruct",
    messages=[
        {
            "role":"user", 
            "content":"Hello! How are you?"
        }
    ],
    max_tokens=2048,
    stream=False
)

completion = response.choices[0].message.content
print(completion)
```