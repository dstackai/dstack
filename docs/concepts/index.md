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

Here's an example from the [Quick start](https://docs.dstack.ai/quick-start).

```yaml
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

YAML-defined workflows eliminate the need to modify code in your scripts, giving you the freedom to choose frameworks,
experiment trackers, and cloud providers.

!!! info "NOTE:"
    Workflows run in containers with pre-configured Conda environments, and CUDA drivers.

## Artifacts

Artifacts enable you to save any files produced by a workflow for later reuse in other workflows. They may include data,
model checkpoints, or even a pre-configured Conda environment.

When running a workflow locally, the artifacts are saved locally. To push the artifacts of a local to a configured remote,
use the `dstack push` command.

When running a workflow remotely, the artifacts are pushed to the remote automatically.

## CLI

The dstack CLI provides various functionalities such as running workflows, accessing logs, artifacts, and stopping
runs, among others.

 ![](../assets/dstack-cli.png){ width="800" }
 
## Why dstack?

`dstack` enables you to define ML workflows declaratively and run them effortlessly
from your preferred IDE either locally or remotely on any cloud.

Unlike end-to-end MLOps platforms, `dstack` is lightweight, developer-friendly, and designed to facilitate collaboration
without imposing any particular approach.