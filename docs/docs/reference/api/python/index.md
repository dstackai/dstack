# API

The Python API allows for running tasks, services, and managing runs programmatically.

#### Usage example

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
    run_name="my-awesome-run",  # (Optional) If not specified, 
    configuration=task,
    resources=Resources(gpu=GPU(memory="24GB")),
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

## `dstack.api` { #dstack.api data-toc-label="dstack.api" }

### `dstack.api.Client` { #dstack.api.Client data-toc-label="Client" }

::: dstack.api.Client
    options:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.Task` { #dstack.api.Task data-toc-label="Task" }

::: dstack.api.Task
    options:
      show_bases: false
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.Service`  { #dstack.api.Service data-toc-label="Service" }

::: dstack.api.Service
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

### `dstack.api.Client.runs` { #dstack.api.Client.runs data-toc-label="runs" }

::: dstack.api.RunCollection
    options:
      show_symbol_type_heading: true
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.Client.repos` { #dstack.api.Client.repos data-toc-label="repos" }

::: dstack.api.RepoCollection
    options:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

### `dstack.api.Client.backends` { #dstack.api.Client.backends data-toc-label="backends" }

::: dstack.api.BackendCollection
    options:
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 4

<style>
.doc-heading .highlight {
    /* TODO pick color */
    --md-code-hl-name-color: var(--md-typeset-color);
    --md-code-hl-constant-color: var(--md-typeset-color);
}
</style>