# service

The `service` configuration type allows running [services](../../concepts/services.md).

!!! info "Filename"
    Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `serve.dstack.yml` are both acceptable)
    and can be located in the project's root directory or any nested folder.
    Any configuration can be run via [`dstack run`](../cli/index.md#dstack-run).

### Example usage

#### Python version

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

python: "3.11"

commands:
  - python3 -m http.server

port: 8000
```

</div>

#### Disabled authentication

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

#### OpenAI-compatible interface

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

#### Private Docker image

<div editor-title="serve.dstack.yml"> 

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

</div>

#### Replicas and auto-scaling

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

#### Resources

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

### Root properties

#SCHEMA# dstack._internal.core.models.configurations.ServiceConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### model

#SCHEMA# dstack._internal.core.models.gateways.BaseChatModel
    overrides:
      show_root_heading: false
      type:
        required: true

### scaling

#SCHEMA# dstack._internal.core.models.configurations.ScalingSpec
    overrides:
      show_root_heading: false
      type:
        required: true

### resources

#SCHEMA# dstack._internal.core.models.resources.ResourcesSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

### gpu

#SCHEMA# dstack._internal.core.models.resources.GPUSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

### registry_auth

#SCHEMA# dstack._internal.core.models.configurations.RegistryAuth
    overrides:
      show_root_heading: false
      type:
        required: true
