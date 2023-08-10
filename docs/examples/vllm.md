# Serving LLMs with vLLM

Serving LLMs can be slow, even on expensive hardware. This example demonstrates how to utilize the 
[`vllm`](https://vllm.ai/) library to serve LLMs with optimized performance.

## What is vLLM?

`vllm` is an open-source library that significantly increases LLM throughput, thanks to the optimized memory-sharing
algorithm called PageAttention.

The library also offers other benefits such as continuous batching, 
GPU parallelism, streaming output, OpenAI-compatibility, and more.

To try `vllm` with `dstack`, follow the instructions below.

## Defining a profile

!!! info "NOTE:"
    Before using `dstack` with a particular cloud, make sure to [configure](../docs/projects.md) the corresponding project.

Each LLM model requires specific resources. To inform `dstack` about the required resources, you need to 
[define](../docs/reference/profiles.yml.md) a profile via the `.dstack/profiles.yaml` file within your project.

Below is a profile that will provision a cloud instance with `24GB` of memory and a `T4` GPU in the `gcp` project.

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: gcp-t4
    project: gcp
    
    resources:
      memory: 24GB
      gpu:
        name: T4
     
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

Here's the configuration that uses services to run an LLM as an OpenAI-compatible endpoint:

<div editor-title="vllm/serve.dstack.yml"> 

```yaml
type: service

# (Optional) If not specified, it will use your local version
python: "3.11"

# (Required) Create a gateway using `dstack gateway create` and set its address with `dstack secrets add`.
gateway: ${{ secrets.GATEWAY_ADDRESS }}

env:
  # (Required) Specify the name of the model
  - MODEL=facebook/opt-125m
  # (Optional) Specify your Hugging Face token
  - HUGGING_FACE_HUB_TOKEN=

port: 8000

commands:
  - conda install cuda # Required since vLLM will rebuild the CUDA kernel
  - pip install vllm # Takes 5-10 minutes
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
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
$ dstack run . -f vllm/serve.dstack.yml
```

</div>

Once the service is up, you can query the endpoint using the gateway address:

<div class="termy">

```shell
$ curl -X POST --location http://98.71.213.179/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
          "model": "facebook/opt-125m",
          "prompt": "San Francisco is a",
          "max_tokens": 7,
          "temperature": 0
        }'
```

</div>

??? info "Custom domains"
    You can use a custom domain with your service. To do this, create an `A` DNS record that points to the gateway
    address (e.g. `98.71.213.179`). Then, instead of using the gateway address (`98.71.213.179`), 
    specify your domain name as the `GATEWAY_ADDRESS` secret.

For more details on how `vllm` works, check their [documentation](https://vllm.readthedocs.io/).

[Source code](https://github.com/dstackai/dstack-examples){ .md-button .md-button--github }

## Limitations

To use `vllm` with `dstack`, be aware of the following limitations:

1. The `vllm` library currently supports a [limited set](https://vllm.readthedocs.io/en/latest/models/supported_models.html) of LLMs, but Llama 2 is supported.
2. The `vllm` library lacks quantization support. Check the progress [here](https://github.com/vllm-project/vllm/issues/316).