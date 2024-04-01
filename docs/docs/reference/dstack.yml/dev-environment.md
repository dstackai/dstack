# dev-environment

The `dev-environment` configuration type allows running [dev environments](../../concepts/dev-environments.md).

!!! info "Filename"
    Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `dev.dstack.yml` are both acceptable)
    and can be located in the project's root directory or any nested folder.
    Any configuration can be run via [`dstack run`](../cli/index.md#dstack-run).

### Examples

#### Python version

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

python: "3.11"

ide: vscode
```

</div>

#### Docker image

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

image: ghcr.io/huggingface/text-generation-inference:latest

ide: vscode
```

</div>

#### Resources

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

ide: vscode

resources:
  cpu: 16.. # 16 or more CPUs
  memory: 200GB.. # 200GB or more RAM
  gpu: 40GB..80GB:4 # 4 GPUs from 40GB to 80GB
  shm_size: 16GB # 16GB of shared memory
  disk: 500GB
```

</div>

#### Environment variables

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

env:
  - HUGGING_FACE_HUB_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1

ide: vscode
```

</div>

#### Private Docker image

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

image: ghcr.io/huggingface/text-generation-inference:latest
registry_auth:
  username: peterschmidt85
  password: ghp_e49HcZ9oYwBzUbcSk2080gXZOU2hiT9AeSR5

ide: vscode
```

</div>

#### Initialization commands

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

python: "3.11"

ide: vscode

init: pip install -r requirements.txt
```

</div>

### Root properties

#SCHEMA# dstack._internal.core.models.configurations.DevEnvironmentConfiguration
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
