# `task`

The `task` configuration type allows running [tasks](../../concepts/tasks.md).

## Root reference

#SCHEMA# dstack._internal.core.models.configurations.TaskConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `retry`

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetry
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

#### `resouces.gpu` { #resources-gpu data-toc-label="gpu" }

#SCHEMA# dstack._internal.core.models.resources.GPUSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

#### `resouces.disk` { #resources-disk data-toc-label="disk" }

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

### `volumes[n]` { #_volumes data-toc-label="volumes" }

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

## Examples


[//]: # (See [tasks]&#40;../../tasks.md#configure-ports&#41; for more detail.)



### Distributed tasks

By default, a task runs on a single node. However, you can run it on a cluster of nodes by specifying `nodes`:

<div editor-title="examples/fine-tuning/train.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train-distrib

# The size of the cluster
nodes: 2

python: "3.10"

# Commands of the task
commands:
  - pip install -r requirements.txt
  - torchrun
    --nproc_per_node=$DSTACK_GPUS_PER_NODE
    --node_rank=$DSTACK_NODE_RANK
    --nnodes=$DSTACK_NODES_NUM
    --master_addr=$DSTACK_MASTER_NODE_IP
    --master_port=8008 resnet_ddp.py
    --num_epochs 20

resources:
  gpu: 24GB
```

</div>



### Backends

By default, `dstack` provisions instances in all configured backends. However, you can specify the list of backends:

<div editor-title="train.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

# Use only listed backends
backends: [aws, gcp]
```

</div>

### Regions

By default, `dstack` uses all configured regions. However, you can specify the list of regions:

<div editor-title="train.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

# Use only listed regions
regions: [eu-west-1, eu-west-2]
```

</div>

### Volumes

Volumes allow you to persist data between runs.
To attach a volume, simply specify its name using the `volumes` property and specify where to mount its contents:

<div editor-title="train.dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: vscode    

python: "3.10"

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

# Map the name of the volume to any path
volumes:
  - name: my-new-volume
    path: /volume_data
```

</div>

Once you run this configuration, the contents of the volume will be attached to `/volume_data` inside the task, 
and its contents will persist across runs.

??? Info "Instance volumes"
    If data persistence is not a strict requirement, use can also use
    ephemeral [instance volumes](../../concepts/volumes.md#instance-volumes).

!!! info "Limitations"
    When you're running a dev environment, task, or service with `dstack`, it automatically mounts the project folder contents
    to `/workflow` (and sets that as the current working directory). Right now, `dstack` doesn't allow you to 
    attach volumes to `/workflow` or any of its subdirectories.

The `task` configuration type supports many other options. See below.