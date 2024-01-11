# API

The Python API enables running tasks, services, and managing runs programmatically.

## Usage example

Below is a quick example of submitting a task for running and displaying its logs.

```python
import sys

from dstack.api import Task, GPU, Client, Resources

client = Client.from_config()

task = Task(
    image="ghcr.io/huggingface/text-generation-inference:latest",
    env={"MODEL_ID": "TheBloke/Llama-2-13B-chat-GPTQ"},
    commands=[
        "text-generation-launcher --trust-remote-code --quantize gptq",
    ],
    ports=["80"],
)

run = client.runs.submit(
    run_name="my-awesome-run",  # If not specified, a random name is assigned 
    configuration=task,
    resources=Resources(gpu=GPU(memory="24GB")),
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
    1. The `configuration` argument in the `submit` method can be either `dstack.api.Task` or `dstack.api.Service`. 
    2. If you create `dstack.api.Task` or `dstack.api.Service`, you may specify the `image` argument. If `image` isn't
       specified, the default image will be used. For a private Docker registry, ensure you also pass the `registry_auth` argument.
    3. The `repo` argument in the `submit` method allows the mounting of a local folder, a remote repo, or a
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

::: dstack.api._TaskConfiguration
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.Service`  { #dstack.api.Service data-toc-label="Service" }

::: dstack.api._ServiceConfiguration
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.Run` { ##dstack.api.Run data-toc-label="Run" }

::: dstack.api.Run
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.Resources` { ##dstack.api.Resources data-toc-label="Resources" }

::: dstack.api._ProfileResources
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.GPU` { ##dstack.api.GPU data-toc-label="GPU" }

::: dstack.api._ProfileGPU
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.Disk` { ##dstack.api.Disk data-toc-label="Disk" }

::: dstack.api._ProfileDisk
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.LocalRepo` { ##dstack.api.LocalRepo data-toc-label="LocalRepo" }

::: dstack.api.LocalRepo
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.RemoteRepo` { ##dstack.api.RemoteRepo data-toc-label="RemoteRepo" }

::: dstack.api.RemoteRepo
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.VirtualRepo` { ##dstack.api.VirtualRepo data-toc-label="VirtualRepo" }

::: dstack.api.VirtualRepo
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.RegistryAuth` { ##dstack.api.RegistryAuth data-toc-label="RegistryAuth" }

::: dstack.api.RegistryAuth
    options:
      show_bases: false
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