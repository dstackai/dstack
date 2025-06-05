# Python API

The Python API enables running tasks, services, and managing runs programmatically.

## Usage example

Below is a quick example of submitting a task for running and displaying its logs.

```python
import sys

from dstack.api import Task, GPU, Client, Resources

client = Client.from_config()

task = Task(
    name="my-awesome-run",  # If not specified, a random name is assigned 
    image="ghcr.io/huggingface/text-generation-inference:latest",
    env={"MODEL_ID": "TheBloke/Llama-2-13B-chat-GPTQ"},
    commands=[
        "text-generation-launcher --trust-remote-code --quantize gptq",
    ],
    ports=["80"],
    resources=Resources(gpu=GPU(memory="24GB")),
)

run = client.runs.apply_configuration(
    configuration=task,
    repo=None, # Specify to mount additional files
)

run.attach()

try:
    for log in run.logs():
        sys.stdout.buffer.write(log)
        sys.stdout.buffer.flush()
except KeyboardInterrupt:
    run.stop(abort=True)
finally:
    run.detach()
```

!!! info "NOTE:"
    1. The `configuration` argument in the `apply_configuration` method can be either `dstack.api.Task`, `dstack.api.Service`, or `dstack.api.DevEnvironment`. 
    2. When you create `dstack.api.Task`, `dstack.api.Service`, or `dstack.api.DevEnvironment`, you can specify the `image` argument. If `image` isn't specified, the default image will be used. For a private Docker registry, ensure you also pass the `registry_auth` argument.
    3. The `repo` argument in the `apply_configuration` method allows the mounting of a local folder, a remote repo, or a
       programmatically created repo. In this case, the `commands` argument can refer to the files within this repo.
    4. The `attach` method waits for the run to start and, for `dstack.api.Task` sets up an SSH tunnel and forwards
    configured `ports` to `localhost`.

## `dstack.api` { #dstack.api data-toc-label="dstack.api" }

### `dstack.api.Client` { #dstack.api.Client data-toc-label="Client" }

::: dstack.api.Client
    options:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.RunCollection` { #dstack.api.Client.runs data-toc-label="RunCollection" }

::: dstack.api.RunCollection
    options:
      show_bases: false
      show_symbol_type_heading: true
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.RepoCollection` { #dstack.api.Client.repos data-toc-label="RepoCollection" }

::: dstack.api.RepoCollection
    options:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

[//]: # (### `dstack.api.BackendCollection` { #dstack.api.Client.backends data-toc-label="BackendCollection" })

[//]: # (::: dstack.api.BackendCollection)
[//]: # (    options:)
[//]: # (      show_bases: false)
[//]: # (      show_root_heading: false)
[//]: # (      show_root_toc_entry: false)
[//]: # (      heading_level: 4)

### `dstack.api.Task` { #dstack.api.Task data-toc-label="Task" }

#SCHEMA# dstack.api.Task
    overrides:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4
      item_id_mapping:
        registry_auth: dstack.api.RegistryAuth
        resources: dstack.api.Resources

### `dstack.api.Service`  { #dstack.api.Service data-toc-label="Service" }

#SCHEMA# dstack.api.Service
    overrides:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4
      item_id_mapping:
        scaling: dstack.api.Scaling
        registry_auth: dstack.api.RegistryAuth
        resources: dstack.api.Resources

### `dstack.api.DevEnvironment` { #dstack.api.DevEnvironment data-toc-label="DevEnvironment" }

#SCHEMA# dstack.api.DevEnvironment
    overrides:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4
      item_id_mapping:
        registry_auth: dstack.api.RegistryAuth
        resources: dstack.api.Resources

### `dstack.api.Run` { #dstack.api.Run data-toc-label="Run" }

::: dstack.api.Run
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.Resources` { #dstack.api.Resources data-toc-label="Resources" }

#SCHEMA# dstack.api.Resources
    overrides:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4
      item_id_mapping:
        cpu: dstack.api.CPU
        gpu: dstack.api.GPU
        memory: dstack.api.Memory
        Range: dstack.api.Range

### `dstack.api.CPU` { #dstack.api.CPU data-toc-label="CPU" }

#SCHEMA# dstack.api.CPU
    overrides:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4
      item_id_mapping:
        Range: dstack.api.Range

### `dstack.api.GPU` { #dstack.api.GPU data-toc-label="GPU" }

#SCHEMA# dstack.api.GPU
    overrides:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4
      item_id_mapping:
        memory: dstack.api.Memory
        Range: dstack.api.Range

### `dstack.api.Disk` { #dstack.api.Disk data-toc-label="Disk" }

#SCHEMA# dstack.api.Disk
    overrides:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4
      item_id_mapping:
        memory: dstack.api.Memory
        Range: dstack.api.Range

### `dstack.api.LocalRepo` { #dstack.api.LocalRepo data-toc-label="LocalRepo" }

::: dstack.api.LocalRepo
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.RemoteRepo` { #dstack.api.RemoteRepo data-toc-label="RemoteRepo" }

::: dstack.api.RemoteRepo
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.VirtualRepo` { #dstack.api.VirtualRepo data-toc-label="VirtualRepo" }

::: dstack.api.VirtualRepo
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.RegistryAuth` { #dstack.api.RegistryAuth data-toc-label="RegistryAuth" }

#SCHEMA# dstack.api.RegistryAuth
    overrides:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.Scaling` { #dstack.api.Scaling data-toc-label="Scaling" }

#SCHEMA# dstack.api.Scaling
    overrides:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.BackendType` { #dstack.api.BackendType data-toc-label="BackendType" }

::: dstack.api.BackendType
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

<style>
.doc-heading .highlight {
    /* TODO pick color */
    --md-code-hl-name-color: var(--md-typeset-color);
    --md-code-hl-constant-color: var(--md-typeset-color);
}

.doc-symbol:after {
    display: none
}

</style>
