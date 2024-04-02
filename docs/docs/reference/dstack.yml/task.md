# task

The `task` configuration type allows running [tasks](../../concepts/tasks.md).

!!! info "Filename"
    Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `train.dstack.yml` are both acceptable)
    and can be located in the project's root directory or any nested folder.
    Any configuration can be run via [`dstack run`](../cli/index.md#dstack-run).

### Examples

#### Python version

If you don't specify `image`, `dstack` uses the default Docker image pre-configured with 
`python`, `pip`, `conda` (Miniforge), and essential CUDA drivers. 
The `python` property determines which default Docker image is used.

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11"

commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
```

</div>

??? info "nvcc"
    Note that the default Docker image doesn't bundle `nvcc`, which is required for building custom CUDA kernels. 
    To install it, use `conda install cuda`.

#### Ports { #_ports }

A task can configure ports. In this case, if the task is running an application on a port, `dstack run` 
will securely allow you to access this port from your local machine through port forwarding.

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

When running it, `dstack run` forwards `6000` port to `localhost:6000`, enabling secure access.
See [tasks](../../concepts/tasks.md#configure-ports) for more detail.

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

??? info "Private registry"
    Use the `registry_auth` property to provide credentials for a private Docker registry.

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

#### Resources { #_resources }

If you specify memory size, you can either specify an explicit size (e.g. `24GB`) or a 
range (e.g. `24GB..`, or `24GB..80GB`, or `..80GB`).

<div editor-title=".dstack.yml"> 

```yaml
type: task

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

The `gpu` property allows specifying not only memory size but also GPU names
and their quantity. Examples: `A100` (one A100), `A10G,A100` (either A10G or A100), 
`A100:80GB` (one A100 of 80GB), `A100:2` (two A100), `24GB..40GB:2` (two GPUs between 24GB and 40GB), 
`A100:40GB:2` (two A100 GPUs of 40GB).

??? info "Shared memory"
    If you are using parallel communicating processes (e.g., dataloaders in PyTorch), you may need to configure 
    `shm_size`, e.g. set it to `16GB`.

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

If you don't assign a value to an environment variable (see `HUGGING_FACE_HUB_TOKEN` above), 
`dstack` will require the value to be passed via the CLI or set in the current process.

For instance, you can define environment variables in a `.env` file and utilize tools like `direnv`.

#### Run arguments

You can parameterize tasks with user arguments using `${{ run.args }}` in the configuration.

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11"

commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py ${{ run.args }}
```

</div>

Now, you can pass your arguments to the `dstack run` command. 
See [tasks](../../concepts/tasks.md#parametrize-tasks) for more detail.

#### Web applications

Here's an example of using `ports` to run web apps with `tasks`. 

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

### Root reference

#SCHEMA# dstack._internal.core.models.configurations.TaskConfiguration
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
      item_id_prefix: resources-

### `resouces.gpu` { #resources-gpu data-toc-label="resources.gpu" }

#SCHEMA# dstack._internal.core.models.resources.GPUSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

### `resouces.disk` { #resources-disk data-toc-label="resources.disk" }

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
