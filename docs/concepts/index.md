# Concepts 

`dstack` allows YAML-defined ML workflows to be run locally or remotely in any configured cloud accounts via CLI.

## Remotes

By default, workflows run locally. To run workflows remotely, you need to first configure a remote using the `dstack
config` command. Once a remote is configured, use the `--remote` flag with the `dstack run` command to run a workflow in
the remote.

!!! info "NOTE:"
    When running a workflow remotely, `dstack` automatically creates and
    destroys cloud instances based on resource requirements and cost strategy, such as using spot instances.

Remotes facilitate collaboration as they allow multiple team members to access the same runs.

## Workflows

Workflows can be scripts for data preparation or model training, web apps like Streamlit or Gradio, or development
environments like JupyterLab or VS Code.

Here's an example from the [Quick start](https://docs.dstack.ai/quick-start):

<div editor-title=".dstack/workflows/mnist.yaml"> 

```yaml hl_lines="8 13 18"
workflows:
  - name: mnist-data
    provider: bash
    commands:
      - pip install torchvision
      - python mnist/mnist_data.py
    artifacts:
      - path: ./data

  - name: train-mnist
    provider: bash
    deps:
      - workflow: mnist-data
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - python mnist/train_mnist.py
    artifacts:
      - path: ./lightning_logs
```

</div>

YAML-defined workflows eliminate the need to modify code in your scripts, giving you the freedom to choose frameworks,
experiment trackers, and cloud providers.

!!! info "NOTE:"
    Workflows run in containers with pre-configured Conda environments, and CUDA drivers.

## Artifacts

When running a workflow locally, the artifacts are stored in `~/.dstack/artifacts` and can only be reused from workflows
that also run locally. To reuse the artifacts remotely, you must push them using the [`dstack push`](../reference/cli/push.md) command.

When running a workflow remotely, the resulting artifacts are automatically stored remotely. If you want to access the
artifacts of a remote workflow locally, you can use the [`dstack pull`](../reference/cli/pull.md) command.

To conveniently refer to the artifacts of a particular run, you can assign a tag to it using
the [`dstack tags`](../reference/cli/tags.md) command.

## CLI

The dstack CLI provides various functionalities such as running workflows, accessing logs, artifacts, and stopping
runs, among others.

<div class="termy">

```shell
$ dstack

Usage: dstack [-v] [-h] COMMAND ...

Positional Arguments:
  COMMAND
    config       Configure the remote backend
    cp           Copy artifact files to a local target path
    init         Authorize dstack to access the current Git repo
    logs         Show logs
    ls           List artifacts
    ps           List runs
    pull         Pull artifacts of a remote run
    push         Push artifacts of a local run
    rm           Remove run(s)
    run          Run a workflow
    secrets      Manage secrets
    stop         Stop run(s)
    tags         Manage tags

Optional Arguments:
  -v, --version  Show dstack version
  -h, --help     Show this help message and exit

Run dstack COMMAND --help for more information on a particular command
```

</div>
 
## Why dstack?

`dstack` enables you to define ML workflows declaratively and run them effortlessly
from your preferred IDE either locally or remotely on any cloud.

Unlike end-to-end MLOps platforms, `dstack` is lightweight, developer-friendly, and designed to facilitate collaboration
without imposing any particular approach.