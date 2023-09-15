# Deploying LLMs using TGI

The example below demonstrates how to use `dstack` to deploy an LLM as a service using TGI. 

??? info "About services"
    [Services](../docs/guides/services.md) allow running web-based applications as public endpoints. This is the recommended way to deploy LLMs for
    production purposes. If you want to run web applications for development purposes, you can also consider running them as [tasks](../docs/guides/tasks.md).

??? info "About TGI"
    [Text Generation Inference](https://github.com/huggingface/text-generation-inference) (TGI) is an open-source framework by Hugging Face for serving LLMs that increases throughput, supports continuous batching, 
    GPU parallelism, streaming output, quantization, etc.

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
    Before running a service, ensure that you have configured a [gateway](../docs/guides/clouds.md#configuring-gateways).

<div class="termy">

```shell
$ dstack run . -f text-generation-inference/serve.dstack.yml --gpu 24GB
```

</div>

!!! info "Wildcard domain"
    If you've configured a [wildcard domain](../docs/guides/clouds.md#configuring-gateways) for the gateway, 
    `dstack` enables HTTPS automatically and serves the service at 
    `https://<run name>.<your domain name>`.

    If you wish to customize the run name, you can use the `-n` argument with the `dstack run` command.

Once the service is up, you can query it:

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

!!! info "Hugging Face Hub token"

    To use a model with gated access, ensure configuring either the `HUGGING_FACE_HUB_TOKEN` secret
    (using [`dstack secrets`](../docs/reference/cli/secrets.md#dstack-secrets-add)),
    or environment variable (with [`--env`](../docs/reference/cli/run.md#ENV) in `dstack run` or 
    using [`env`](../docs/reference/dstack.yml/service.md#env) in the configuration file).
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f text-generation-inference/serve.dstack.yml --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; --gpu 24GB
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

!!! info "Source code"
    The complete, ready-to-run code is available in [dstackai/dstack-examples](https://github.com/dstackai/dstack-examples).