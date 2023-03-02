# How dstack works 

`dstack` enables you to define ML pipelines in YAML and run them through CLI.
You can run them either locally or remotely, for instance, in any configured cloud account, without the need for
Kubernetes or custom Docker images.

When you run a workflow remotely in a configured cloud account, `dstack` creates and destroys instances automatically, 
based on the resource requirements. The workflows run in containers that have pre-configured Conda environments, 
CUDA drivers, and other necessary components. To optimize costs, `dstack` offers the option of using spot instances.

## Workflows

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

As workflows are defined using YAML, there's no need for modifying the code in your scripts. You have the freedom to
choose any frameworks, experiment trackers, or cloud providers.

Workflows can take the form of regular scripts, which may involve tasks such as data preparation or model training, as
well as web applications such as Streamlit or Gradle. Additionally, they can also be development environments such as
JupyterLab or VS Code.

## Remotes

By default, workflows run locally. However, to run workflows remotely (such as in a cloud), you need to
configure a remote by using the `dstack config` command and then use the `--remote` flag with the `dstack run` command.

!!! info "NOTE:"
    Currently, `dstack` supports AWS and GCP as remotes. Support for Azure and Hub are coming soon.

If multiple members on your team have the same remote configured, they can see each other's runs and reuse 
each other's artifacts.

## Artifacts

Artifacts can be utilized to preserve the output of a workflow for later use in other workflows. Artifacts may comprise
data, model checkpoints, or even a pre-configured Conda environment.

When executing a workflow locally, the artifacts are saved locally. If you want to use the artifacts of a local run
outside your machine, you can push them to a configured remote using the `dstack push` command.

When running a workflow remotely, the artifacts are automatically pushed to the remote.

## CLI

The dstack CLI provides various functionalities such as running workflows, accessing logs, artifacts, and stopping
runs, among others.

 ![](../assets/dstack-cli.png){ width="800" }
 
## Why dstack?

`dstack` enables you to create ML pipelines that are independent of any particular vendor and run them effortlessly
from your preferred IDE.

Unlike end-to-end MLOps platforms, `dstack` is lightweight, developer-friendly, and designed to facilitate collaboration
without imposing any particular approach.