# AMD

Since [0.18.11 :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/releases/0.18.11rc1){:target="_blank"},
you can specify an AMD GPU under `resources`. Below are a few examples.

> AMD accelerators are currently supported only with the [`runpod`](https://dstack.ai/docs/reference/server/config.yml/#runpod) backend.

## Deployment

### Running as a service

=== "TGI"
    Here's an example of a [service](https://dstack.ai/docs/services) that deploys
    Llama 3.1 70B in FP16 using [TGI :material-arrow-top-right-thin:{ .external }](https://huggingface.co/docs/text-generation-inference/en/installation_amd){:target="_blank"}.
    
    <div editor-title="examples/deployment/tgi/amd/service.dstack.yml"> 
    
    ```yaml
    type: service
    name: amd-service-tgi
    
    image: ghcr.io/huggingface/text-generation-inference:sha-a379d55-rocm
    env:
      - HUGGING_FACE_HUB_TOKEN
      - MODEL_ID=meta-llama/Meta-Llama-3.1-70B-Instruct
      - TRUST_REMOTE_CODE=true
      - ROCM_USE_FLASH_ATTN_V2_TRITON=true
    commands:
      - text-generation-launcher --port 8000
    port: 8000
    
    resources:
      gpu: MI300X
      disk: 150GB
    
    spot_policy: auto
    
    model:
      type: chat
      name: meta-llama/Meta-Llama-3.1-70B-Instruct
      format: openai
    ```
    
    </div>

!!! info "Docker image"
    Please note that if you want to use AMD, specifying `image` is currently required. This must be an image that includes
    ROCm drivers.

To request multiple GPUs, specify the quantity after the GPU name, separated by a colon, e.g., `MI300X:4`.

AMD accelerators can also be used with other frameworks like vLLM, Ollama, etc., and we'll be adding more examples soon.

### Running a configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

## Fleets

By default, `dstack apply` reuses `idle` instances from one of the existing [fleets](https://dstack.ai/docs/fleets).
If no `idle` instances meet the requirements, it creates a new fleet using one of the configured backends.

Use [fleets](https://dstack.ai/docs/fleets.md) configurations to create fleets manually. This reduces startup time for dev environments,
tasks, and services, and is very convenient if you want to reuse fleets across runs.

## Dev environments

Before running a task or service, it's recommended that you first start with
a [dev environment](https://dstack.ai/docs/dev-environments). Dev environments
allow you to run commands interactively.

## Source code

The source-code of this example can be found in 
[`examples/deployment/tgi/amd` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/tgi/amd){:target="_blank"}.

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), and
   [services](https://dstack.ai/docs/services).