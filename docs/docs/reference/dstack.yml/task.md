# task

The `task` configuration type allows running [tasks](../../concepts/tasks.md).

!!! info "Filename"
    Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `train.dstack.yml` are both acceptable)
    and can be located in the project's root directory or any nested folder.
    Any configuration can be run via [`dstack run`](../cli/index.md#dstack-run).

### Example usage

#### Python version

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11"

commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
```

</div>

#### Ports

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11"

commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - tensorboard --logdir results/runs &
  - python fine-tuning/qlora/train.py
  
ports:
  - 6000
```

</div>

#### Docker image

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

image: dstackai/base:py3.11-0.4rc4-cuda-12.1

commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
```

</div>

#### Resources

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
  
resources:
  cpu: 16.. # 16 or more CPUs
  memory: 200GB.. # 200GB or more RAM
  gpu: 40GB..80GB:4 # 4 GPUs from 40GB to 80GB
  shm_size: 16GB # 16GB of shared memory
  disk: 500GB
```

</div>

#### Environment variables

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11"

env:
  - HUGGING_FACE_HUB_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1

commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
```

</div>

#### Private Docker image

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

image: dstackai/base:py3.11-0.4rc4-cuda-12.1
registry_auth:
  username: peterschmidt85
  password: ghp_e49HcZ9oYwBzUbcSk2080gXZOU2hiT9AeSR5

commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
```

</div>

#### Run arguments

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11"

commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py ${{ run.args }}
```

</div>

#### Web applications

<div editor-title="app.dstack.yml"> 

```yaml
type: task

python: "3.11"

commands:
  - pip3 install streamlit
  - streamlit hello

ports: 
  - 8501

```

</div>

### Root properties

#SCHEMA# dstack._internal.core.models.configurations.TaskConfiguration
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
