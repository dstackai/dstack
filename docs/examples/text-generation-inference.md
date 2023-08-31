# Serving LLMs with TGI

Serving LLMs can be slow. The example below demonstrates how to use
[Text Generation Inference](https://github.com/huggingface/text-generation-inference) (TGI) to serve LLMs with
optimized performance. 

## What is TGI?

TGI is an open-source tool by Hugging Face that increases LLM throughput, thanks to the optimized memory-sharing
algorithms such as FlashAttention and PageAttention.

The tool also provides other benefits such as continuous batching, 
GPU parallelism, streaming output, quantization, water-marking, and more.

To try TGI with `dstack`, follow the instructions below.

## Define the configuration

??? info "Tasks"
    If you want to serve an application for development purposes only, you can use 
    [tasks](../docs/guides/services.md). 
    In this scenario, while the application runs in the cloud, 
    it is accessible from your local machine only.

For production purposes, the optimal approach to serve an application is by using 
[services](../docs/guides/services.md). In this case, the application can be accessed through a public endpoint.

Here's the configuration that uses services:

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

!!! warning "NOTE:"
    Before running a service, ensure that you have configured a [gateway](../docs/guides/clouds.md#configuring-gateways).

<div class="termy">

```shell
$ dstack run . -f text-generation-inference/serve.dstack.yml --gpu 24GB
```

</div>

!!! info "Endpoint URL"
    If you've configured a [wildcard domain](clouds.md#configuring-gateways) for the gateway, 
    `dstack` enables HTTPS automatically and serves the service at 
    `https://<run name>.<your domain name>`.

    If you wish to customize the run name, you can use the `-n` argument with the `dstack run` command.

Once the service is up, you can query the endpoint:

<div class="termy">

```shell
$ curl -X POST --location https://yellow-cat-1.mydomain.com \
    -H 'Content-Type: application/json' \
    -d '{
          "inputs": "What is Deep Learning?",
          "parameters": {
            "max_new_tokens": 20
          }
        }'
```

</div>

### Gated models

To use a model with gated access, ensure configuring either the `HUGGING_FACE_HUB_TOKEN` secret
(using [`dstack secrets`](../docs/reference/cli/secrets.md#dstack-secrets-add)),
or environment variable (with [`--env`](../docs/reference/cli/run.md#ENV) in `dstack run` or 
using [`env`](../docs/reference/dstack.yml/service.md#env) in the configuration file).

<div class="termy">

```shell
$ dstack run . -f text-generation-inference/serve.dstack.yml --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; --gpu 24GB
```
</div>

### Memory usage and quantization

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

A similar approach allows running the Llama 2 70B model on an `80GB` GPU (A100).

To calculate the exact GPU memory required for a specific model with different quantization methods, you can use the
[hf-accelerate/memory-model-usage](https://huggingface.co/spaces/hf-accelerate/model-memory-usage) Space.

??? info "Dev environments"

    Dev environments require the Docker image to have `openssh-server` pre-installed. 
    While `dstack`'s default Docker images include it, the `ghcr.io/huggingface/text-generation-inference` Docker 
    image lacks it. Therefore, ensure that you manually install `openssh-server` using the `build` property.
    
    <div editor-title="text-generation-inference/.dstack.yml">
    
    ```yaml
    type: dev-environment
    
    image: ghcr.io/huggingface/text-generation-inference:latest
    
    build:
      - apt-get update
      - DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server
      - rm -rf /var/lib/apt/lists/*
    
    ide: vscode
    ```
    
    </div>

[Source code](https://github.com/dstackai/dstack-examples){ .md-button .md-button--github }
