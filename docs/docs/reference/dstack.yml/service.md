# service

The `service` configuration type allows running [services](../../concepts/services.md).

!!! info "Filename"
    Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `serve.dstack.yml` are both acceptable)
    and can be located in the project's root directory or any nested folder.
    Any configuration can be run via [`dstack run`](../cli/index.md#dstack-run).

### Examples

#### Python version

If you don't specify `image`, `dstack` uses the default Docker image pre-configured with 
`python`, `pip`, `conda` (Miniforge), and essential CUDA drivers. 
The `python` property determines which default Docker image is used.

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

python: "3.11"

commands:
  - python3 -m http.server

port: 8000
```

</div>

??? info "nvcc"
    Note that the default Docker image doesn't bundle `nvcc`, which is required for building custom CUDA kernels. 
    To install it, use `conda install cuda`.

#### Docker image

<div editor-title="serve.dstack.yml">

    ```yaml
    type: service
    
    image: dstackai/base:py3.11-0.4rc4-cuda-12.1
    
    commands:
      - python3 -m http.server
      
    port: 8000
    ```

</div>

??? info "Private Docker registry"
    
    Use the `registry_auth` property to provide credentials for a private Docker registry.

    ```yaml
    type: service
    
    image: dstackai/base:py3.11-0.4rc4-cuda-12.1
    
    commands:
      - python3 -m http.server
    registry_auth:
      username: peterschmidt85
      password: ghp_e49HcZ9oYwBzUbcSk2080gXZOU2hiT9AeSR5
      
    port: 8000
    ```

#### OpenAI-compatible interface

By default, if you run a service, its endpoint is accessible at `https://<run name>.<gateway domain>`.

If you run a model, you can optionally configure the mapping to make it accessible via the 
OpenAI-compatible interface.

<div editor-title="serve.dstack.yml"> 

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

# Enable the OpenAI-compatible endpoint
model:
  format: openai
  type: chat
  name: NousResearch/Llama-2-7b-chat-hf
```

</div>

In this case, with such a configuration, once the service is up, you'll be able to access the model at
`https://gateway.<gateway domain>` via the OpenAI-compatible interface.
See [services](../../concepts/services.md#configure-model-mapping) for more detail.

#### Replicas and auto-scaling

By default, `dstack` runs a single replica of the service.
You can configure the number of replicas as well as the auto-scaling policy.

<div editor-title="serve.dstack.yml"> 

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

# Enable the OpenAI-compatible endpoint
model:
  format: openai
  type: chat
  name: NousResearch/Llama-2-7b-chat-hf

replicas: 1..4
scaling:
  metric: rps
  target: 10
```

</div>

If you specify the minimum number of replicas as `0`, the service will scale down to zero when there are no requests.

#### Resources { #_resources }

If you specify memory size, you can either specify an explicit size (e.g. `24GB`) or a 
range (e.g. `24GB..`, or `24GB..80GB`, or `..80GB`).

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

python: "3.11"
commands:
  - pip install vllm
  - python -m vllm.entrypoints.openai.api_server
    --model mistralai/Mixtral-8X7B-Instruct-v0.1
    --host 0.0.0.0
    --tensor-parallel-size 2 # Match the number of GPUs
port: 8000

resources:
  gpu: 80GB:2 # 2 GPUs of 80GB
  disk: 200GB

# Enable the OpenAI-compatible endpoint
model:
  type: chat
  name: TheBloke/Mixtral-8x7B-Instruct-v0.1-GPTQ
  format: openai
```

</div>

The `gpu` property allows specifying not only memory size but also GPU names
and their quantity. Examples: `A100` (one A100), `A10G,A100` (either A10G or A100), 
`A100:80GB` (one A100 of 80GB), `A100:2` (two A100), `24GB..40GB:2` (two GPUs between 24GB and 40GB), 
`A100:40GB:2` (two A100 GPUs of 40GB).

??? info "Shared memory"
    If you are using parallel communicating processes (e.g., dataloaders in PyTorch), you may need to configure 
    `shm_size`, e.g. set it to `16GB`.

#### Authentication

By default, the service endpoint requires the `Authentication` header with `"Bearer <dstack token>"`.
Authentication can be disabled by setting `auth` to `false`.

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

python: "3.11"

commands:
  - python3 -m http.server

port: 8000

auth: false
```

</div>

### Root reference

#SCHEMA# dstack._internal.core.models.configurations.ServiceConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `model`

#SCHEMA# dstack._internal.core.models.gateways.BaseChatModel
    overrides:
      show_root_heading: false
      type:
        required: true

### `scaling`

#SCHEMA# dstack._internal.core.models.configurations.ScalingSpec
    overrides:
      show_root_heading: false
      type:
        required: true

### `resources`

#SCHEMA# dstack._internal.core.models.resources.ResourcesSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

### `resouces.gpu` { #gpu data-toc-label="gpu" } 

#SCHEMA# dstack._internal.core.models.resources.GPUSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

### `resouces.disk` { #disk data-toc-label="disk" }

#SCHEMA# dstack._internal.core.models.resources.DiskSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

### `registry_auth`

#SCHEMA# dstack._internal.core.models.configurations.RegistryAuth
    overrides:
      show_root_heading: false
      type:
        required: true
