# service

The `service` configuration type allows running [services](../../services.md).

> Configuration files must be inside the project repo, and their names must end with `.dstack.yml` 
> (e.g. `.dstack.yml` or `serve.dstack.yml` are both acceptable).
> Any configuration can be run via [`dstack apply`](../cli/index.md#dstack-apply).

## Examples

### Python version

If you don't specify `image`, `dstack` uses its base Docker image pre-configured with 
`python`, `pip`, `conda` (Miniforge), and essential CUDA drivers. 
The `python` property determines which default Docker image is used.

<div editor-title="service.dstack.yml"> 

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: http-server-service    

# If `image` is not specified, dstack uses its base image
python: "3.10"

# Commands of the service
commands:
  - python3 -m http.server
# The port of the service
port: 8000
```

</div>

??? info "nvcc"
    By default, the base Docker image doesn’t include `nvcc`, which is required for building custom CUDA kernels. 
    If you need `nvcc`, set the corresponding property to true.

    <div editor-title="service.dstack.yml"> 

    ```yaml
    type: service
    # The name is optional, if not specified, generated randomly
    name: http-server-service    
    
    # If `image` is not specified, dstack uses its base image
    python: "3.10"
    # Ensure nvcc is installed (req. for Flash Attention) 
    nvcc: true

     # Commands of the service
    commands:
      - python3 -m http.server
    # The port of the service
    port: 8000
    ```
    
    </div>

### Docker

If you want, you can specify your own Docker image via `image`.

<div editor-title="service.dstack.yml">

    ```yaml
    type: service
    # The name is optional, if not specified, generated randomly
    name: http-server-service

    # Any custom Docker image
    image: dstackai/base:py3.13-0.6-cuda-12.1
    
    # Commands of the service
    commands:
      - python3 -m http.server
    # The port of the service
    port: 8000
    ```

</div>

??? info "Private Docker registry"
    
    Use the `registry_auth` property to provide credentials for a private Docker registry.

    ```yaml
    type: service
    # The name is optional, if not specified, generated randomly
    name: http-server-service
    
    # Any private Docker iamge
    image: dstackai/base:py3.13-0.6-cuda-12.1
    # Credentials of the private registry
    registry_auth:
      username: peterschmidt85
      password: ghp_e49HcZ9oYwBzUbcSk2080gXZOU2hiT9AeSR5
    
    # Commands of the service  
    commands:
      - python3 -m http.server
    # The port of the service
    port: 8000
    ```

!!! info "Docker and Docker Compose"
    All backends except `runpod`, `vastai` and `kubernetes` also allow to use [Docker and Docker Compose](../../guides/protips.md#docker-and-docker-compose) 
    inside `dstack` runs.

### Models { #model-mapping }

If you are running a chat model with an OpenAI-compatible interface,
set the [`model`](#model) property to make the model accessible via
the OpenAI-compatible endpoint provided by `dstack`.

<div editor-title="service.dstack.yml"> 

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: llama31-service

python: "3.10"

# Required environment variables
env:
  - HF_TOKEN
commands:
  - pip install vllm
  - vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct --max-model-len 4096
# Expose the port of the service
port: 8000

resources:
  # Change to what is required
  gpu: 24GB

# Register the model
model: meta-llama/Meta-Llama-3.1-8B-Instruct

# Alternatively, use this syntax to set more model settings:
# model:
#   type: chat
#   name: meta-llama/Meta-Llama-3.1-8B-Instruct
#   format: openai
#   prefix: /v1
```

</div>

Once the service is up, the model will be available via the OpenAI-compatible endpoint
at `<dstack server URL>/proxy/models/<project name>`
or at `https://gateway.<gateway domain>` if your project has a gateway.

### Auto-scaling

By default, `dstack` runs a single replica of the service.
You can configure the number of replicas as well as the auto-scaling rules.

<div editor-title="service.dstack.yml"> 

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: llama31-service

python: "3.10"

# Required environment variables
env:
  - HF_TOKEN
commands:
  - pip install vllm
  - vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct --max-model-len 4096
# Expose the port of the service
port: 8000

resources:
  # Change to what is required
  gpu: 24GB

# Minimum and maximum number of replicas
replicas: 1..4
scaling:
  # Requests per seconds
  metric: rps
  # Target metric value
  target: 10
```

</div>

The [`replicas`](#replicas) property can be a number or a range.

> The [`metric`](#metric) property of [`scaling`](#scaling) only supports the `rps` metric (requests per second). In this 
> case `dstack` adjusts the number of replicas (scales up or down) automatically based on the load. 

Setting the minimum number of replicas to `0` allows the service to scale down to zero when there are no requests.

!!! info "Gateway"
    Services with a fixed number of replicas are supported both with and without a
    [gateway](../../concepts/gateways.md).
    Auto-scaling is currently only supported for services running with a gateway.

### Resources { #_resources }

If you specify memory size, you can either specify an explicit size (e.g. `24GB`) or a 
range (e.g. `24GB..`, or `24GB..80GB`, or `..80GB`).

<div editor-title="examples/llms/mixtral/vllm.dstack.yml"> 

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: http-server-service

python: "3.10"

# Commands of the service
commands:
  - pip install vllm
  - python -m vllm.entrypoints.openai.api_server
    --model mistralai/Mixtral-8X7B-Instruct-v0.1
    --host 0.0.0.0
    --tensor-parallel-size $DSTACK_GPUS_NUM
# Expose the port of the service
port: 8000

resources:
  # 2 GPUs of 80GB
  gpu: 80GB:2

  # Minimum disk size
  disk: 200GB
```

</div>

The `gpu` property allows specifying not only memory size but also GPU vendor, names
and their quantity. Examples: `nvidia` (one NVIDIA GPU), `A100` (one A100), `A10G,A100` (either A10G or A100),
`A100:80GB` (one A100 of 80GB), `A100:2` (two A100), `24GB..40GB:2` (two GPUs between 24GB and 40GB),
`A100:40GB:2` (two A100 GPUs of 40GB).

??? info "Shared memory"
    If you are using parallel communicating processes (e.g., dataloaders in PyTorch), you may need to configure 
    `shm_size`, e.g. set it to `16GB`.

### Authorization

By default, the service endpoint requires the `Authorization` header with `"Bearer <dstack token>"`.
Authorization can be disabled by setting `auth` to `false`.

<div editor-title="examples/misc/http.server/service.dstack.yml"> 

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: http-server-service

# Disable authorization
auth: false

python: "3.10"

# Commands of the service
commands:
  - python3 -m http.server
# The port of the service
port: 8000
```

</div>

### Environment variables

<div editor-title="service.dstack.yml">

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: llama-2-7b-service

python: "3.10"

# Environment variables
env:
  - HF_TOKEN
  - MODEL=NousResearch/Llama-2-7b-chat-hf
# Commands of the service
commands:
  - pip install vllm
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
# The port of the service
port: 8000

resources:
  # Required GPU vRAM
  gpu: 24GB
```

</div>

If you don't assign a value to an environment variable (see `HF_TOKEN` above),
`dstack` will require the value to be passed via the CLI or set in the current process.

For instance, you can define environment variables in a `.envrc` file and utilize tools like `direnv`.

#### System environment variables

The following environment variables are available in any run and are passed by `dstack` by default:

| Name                    | Description                             |
|-------------------------|-----------------------------------------|
| `DSTACK_RUN_NAME`       | The name of the run                     |
| `DSTACK_REPO_ID`        | The ID of the repo                      |
| `DSTACK_GPUS_NUM`       | The total number of GPUs in the run     |

### Spot policy

You can choose whether to use spot instances, on-demand instances, or any available type.

<div editor-title="service.dstack.yml">

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: http-server-service

commands:
  - python3 -m http.server
# The port of the service
port: 8000

# Uncomment to leverage spot instances
#spot_policy: auto
```

</div>

The `spot_policy` accepts `spot`, `on-demand`, and `auto`. The default for services is `on-demand`.

### Backends

By default, `dstack` provisions instances in all configured backends. However, you can specify the list of backends:

<div editor-title="service.dstack.yml">

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: http-server-service

# Commands of the service
commands:
  - python3 -m http.server
# The port of the service
port: 8000

# Use only listed backends
backends: [aws, gcp]
```

</div>

### Regions

By default, `dstack` uses all configured regions. However, you can specify the list of regions:

<div editor-title="service.dstack.yml">

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: http-server-service

# Commands of the service
commands:
  - python3 -m http.server
# The port of the service
port: 8000

# Use only listed regions
regions: [eu-west-1, eu-west-2]
```

</div>

### Volumes

Volumes allow you to persist data between runs.
To attach a volume, simply specify its name using the `volumes` property and specify where to mount its contents:

<div editor-title="service.dstack.yml"> 

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: http-server-service

# Commands of the service
commands:
  - python3 -m http.server
# The port of the service
port: 8000

# Map the name of the volume to any path
volumes:
  - name: my-new-volume
    path: /volume_data
```

</div>

Once you run this configuration, the contents of the volume will be attached to `/volume_data` inside the service, 
and its contents will persist across runs.

??? Info "Instance volumes"
    If data persistence is not a strict requirement, use can also use
    ephemeral [instance volumes](../../concepts/volumes.md#instance-volumes).

!!! info "Limitations"
    When you're running a dev environment, task, or service with `dstack`, it automatically mounts the project folder contents
    to `/workflow` (and sets that as the current working directory). Right now, `dstack` doesn't allow you to
    attach volumes to `/workflow` or any of its subdirectories.

The `service` configuration type supports many other options. See below.

## Root reference

#SCHEMA# dstack._internal.core.models.configurations.ServiceConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

## `model[format=openai]`

#SCHEMA# dstack._internal.core.models.gateways.OpenAIChatModel
    overrides:
      show_root_heading: false
      type:
        required: true

## `model[format=tgi]`

> TGI provides an OpenAI-compatible API starting with version 1.4.0,
so models served by TGI can be defined with `format: openai` too.

#SCHEMA# dstack._internal.core.models.gateways.TGIChatModel
    overrides:
      show_root_heading: false
      type:
        required: true

??? info "Chat template"

    By default, `dstack` loads the [chat template](https://huggingface.co/docs/transformers/main/en/chat_templating)
    from the model's repository. If it is not present there, manual configuration is required.

    ```yaml
    type: service

    image: ghcr.io/huggingface/text-generation-inference:latest
    env:
      - MODEL_ID=TheBloke/Llama-2-13B-chat-GPTQ
    commands:
      - text-generation-launcher --port 8000 --trust-remote-code --quantize gptq
    port: 8000

    resources:
      gpu: 80GB

    # Enable the OpenAI-compatible endpoint
    model:
      type: chat
      name: TheBloke/Llama-2-13B-chat-GPTQ
      format: tgi
      chat_template: "{% if messages[0]['role'] == 'system' %}{% set loop_messages = messages[1:] %}{% set system_message = messages[0]['content'] %}{% else %}{% set loop_messages = messages %}{% set system_message = false %}{% endif %}{% for message in loop_messages %}{% if (message['role'] == 'user') != (loop.index0 % 2 == 0) %}{{ raise_exception('Conversation roles must alternate user/assistant/user/assistant/...') }}{% endif %}{% if loop.index0 == 0 and system_message != false %}{% set content = '<<SYS>>\\n' + system_message + '\\n<</SYS>>\\n\\n' + message['content'] %}{% else %}{% set content = message['content'] %}{% endif %}{% if message['role'] == 'user' %}{{ '<s>[INST] ' + content.strip() + ' [/INST]' }}{% elif message['role'] == 'assistant' %}{{ ' '  + content.strip() + ' </s>' }}{% endif %}{% endfor %}"
      eos_token: "</s>"
    ```

    ##### Limitations

    Please note that model mapping is an experimental feature with the following limitations:

    1. Doesn't work if your `chat_template` uses `bos_token`. As a workaround, replace `bos_token` inside `chat_template` with the token content itself.
    2. Doesn't work if `eos_token` is defined in the model repository as a dictionary. As a workaround, set `eos_token` manually, as shown in the example above (see Chat template).

    If you encounter any other issues, please make sure to file a [GitHub issue](https://github.com/dstackai/dstack/issues/new/choose).

## `scaling`

#SCHEMA# dstack._internal.core.models.configurations.ScalingSpec
    overrides:
      show_root_heading: false
      type:
        required: true

## `resources`

#SCHEMA# dstack._internal.core.models.resources.ResourcesSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true
      item_id_prefix: resources-

## `resouces.gpu` { #resources-gpu data-toc-label="resources.gpu" }

#SCHEMA# dstack._internal.core.models.resources.GPUSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

## `resouces.disk` { #resources-disk data-toc-label="resources.disk" }

#SCHEMA# dstack._internal.core.models.resources.DiskSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

## `registry_auth`

#SCHEMA# dstack._internal.core.models.configurations.RegistryAuth
    overrides:
      show_root_heading: false
      type:
        required: true

## `volumes[n]` { #_volumes data-toc-label="volumes" }

=== "Network volumes"

    #SCHEMA# dstack._internal.core.models.volumes.VolumeMountPoint
        overrides:
          show_root_heading: false
          type:
            required: true

=== "Instance volumes"

    #SCHEMA# dstack._internal.core.models.volumes.InstanceMountPoint
        overrides:
          show_root_heading: false
          type:
            required: true

??? info "Short syntax"

    The short syntax for volumes is a colon-separated string in the form of `source:destination`

    * `volume-name:/container/path` for network volumes
    * `/instance/path:/container/path` for instance volumes
