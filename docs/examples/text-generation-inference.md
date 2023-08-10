# Serving LLMs with TGI

Serving LLMs can be slow, even on expensive hardware. This example demonstrates how to utilize
[Text Generation Inference](https://github.com/huggingface/text-generation-inference) (TGI) to serve LLMs with
optimized performance. 

## What is TGI?

TGI is an open-source tool by Hugging Face that increases LLM throughput, thanks to the optimized memory-sharing
algorithms such as FlashAttention and PageAttention.

The tool also provides other benefits such as continuous batching, 
GPU parallelism, streaming output, quantization, water-marking, and more.

To try TGI with `dstack`, follow the instructions below.

## Defining a profile

!!! info "NOTE:"
    Before using `dstack` with a particular cloud, make sure to [configure](../docs/projects.md) the corresponding project.

Each LLM model requires specific resources. To inform `dstack` about the required resources, you need to 
[define](../docs/reference/profiles.yml.md) a profile via the `.dstack/profiles.yaml` file within your project.

Below is a profile that will provision a cloud instance with `24GB` of memory and a `A10` GPU in the `gcp` project.

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: gcp-a10
    project: gcp
    
    resources:
      memory: 24GB
      gpu:
        name: A10
     
    spot_policy: auto   
      
    default: true
```

</div>

!!! info "Spot instances"
    If `spot_policy` is set to `auto`, `dstack` prioritizes spot instances.
    If these are unavailable, it uses `on-demand` instances. To cut costs, set `spot_policy` to `spot`.

## Running an endpoint

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
# This configuration deploys a given LLM model as an API

# (Required) Create a gateway using `dstack gateway create` and set its address with `dstack secrets add`.
gateway: ${{ secrets.GATEWAY_ADDRESS }}

image: ghcr.io/huggingface/text-generation-inference:1.0.0

env:
  # (Required) Specify the name of the model
  - MODEL_ID=NousResearch/Llama-2-7b-hf
  # (Optional) Specify your Hugging Face token
  - HUGGING_FACE_HUB_TOKEN=

port: 8000

commands: 
  - text-generation-launcher --hostname 0.0.0.0 --port 8000 --trust-remote-code
```

</div>

Before you can run a service, you have to ensure that there is a gateway configured for your project.

??? info "Gateways"
    To create a gateway, use the `dstack gateway create` command:
    
    <div class="termy">
    
    ```shell
    $ dstack gateway create
    
    Creating gateway...
    
     NAME                        ADDRESS    
     dstack-gateway-fast-walrus  98.71.213.179 
    
    ```
    
    </div>
    
    Once the gateway is up, create a secret with the gateway's address.
    
    <div class="termy">
    
    ```shell
    $ dstack secrets add GATEWAY_ADDRESS 98.71.213.179
    ```
    </div>

After the gateway is configured, go ahead run the service.

<div class="termy">

```shell
$ dstack run . -f text-generation-inference/serve.dstack.yml
```

</div>

Once the service is up, you can query the endpoint using the gateway address:

Now, you can query the endpoint:

<div class="termy">

```shell
$ curl -X POST --location http://98.71.213.179/generate \
    -H 'Content-Type: application/json' \
    -d '{
          "inputs": "What is Deep Learning?",
          "parameters": {
            "max_new_tokens": 20
          }
        }'
```

</div>

??? info "Custom domains"
    You can use a custom domain with your service. To do this, create an `A` DNS record that points to the gateway
    address (e.g. `98.71.213.179`). Then, instead of using the gateway address (`98.71.213.179`), 
    specify your domain name as the `GATEWAY_ADDRESS` secret.

For more details on how `text-generation-inference` works, check their [repo](https://github.com/huggingface/text-generation-inference).

## Dev environments

Dev environments require the Docker image to have `openssh-server` pre-installed. 
While `dstack`'s default Docker images include it, the `ghcr.io/huggingface/text-generation-inference` Docker 
image lacks it. Therefore, ensure that you manually install `openssh-server` using the `build` property.

<div editor-title="text-generation-inference/.dstack.yml">

```yaml
type: dev-environment

image: ghcr.io/huggingface/text-generation-inference:1.0.0

build:
  - apt-get update
  - DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server
  - rm -rf /var/lib/apt/lists/*

ide: vscode
```

</div>

!!! info "NOTE:"
    Since version 1.0.0, TGI has [changed](https://github.com/huggingface/text-generation-inference/issues/726) 
    the license. This means that you cannot use TGI to provide the API as a service, although you can still use TGI for commercial purposes.

[Source code](https://github.com/dstackai/dstack-examples){ .md-button .md-button--github }
