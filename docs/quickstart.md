---
title: Quickstart
hide: 
  - footer
---

<style>
.md-sidebar--secondary {
  order: 0;
}
.md-sidebar--primary {
  order: 2;
}
</style>

# Quickstart

!!! info "NOTE:"
    The source code of this example is available in the <a href="https://github.com/dstackai/dstack-playground#readme" target="__blank">Playground</a>. 

## Install the CLI

Use `pip` to install `dstack`:

<div class="termy">

```shell
$ pip install dstack
```

</div>

## Create a repo

To use `dstack`, you need at least one remote branch configured in your project hosted on any platform like GitHub,
GitLab, or BitBucket.

??? info "Set up a remote branch"
    If you haven't set up a remote branch in your repo yet, here's how you can do it:

    <div class="termy">
    
    ```shell
    $ echo "# Quick start" >> README.md
    $ git init
    $ git add README.md
    $ git commit -m "first commit"
    $ git branch -M main
    $ git remote add origin "<your remote repo URL>"
    $ git push -u origin main
    ```

    </div>

Then, you need to initialize the repo.

<div class="termy">

```shell
$ dstack init
```

</div>

## Create a script

Let's create the following training script.

<div editor-title="examples/mnist/train_mnist.py"> 

```python
import torch
from pytorch_lightning import LightningModule, Trainer
from pytorch_lightning.callbacks.progress import TQDMProgressBar
from torch.nn import functional as F
from torch.utils.data import DataLoader
from torchvision import transforms
from torchvision.datasets import MNIST


class MNISTModel(LightningModule):
    def __init__(self):
        super().__init__()
        self.l1 = torch.nn.Linear(28 * 28, 10)

    def forward(self, x):
        return torch.relu(self.l1(x.view(x.size(0), -1)))

    def training_step(self, batch, batch_nb):
        x, y = batch
        loss = F.cross_entropy(self(x), y)
        return loss

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=0.02)


BATCH_SIZE = torch.cuda.device_count() * 64 if torch.cuda.is_available() else 64

if __name__ == "__main__":
    # Init our model
    mnist_model = MNISTModel()

    # Init DataLoader from MNIST Dataset
    train_ds = MNIST("./data", train=True, download=True, transform=transforms.ToTensor())
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE)

    # Initialize a trainer
    trainer = Trainer(
        accelerator="auto",
        devices="auto",
        max_epochs=3,
        callbacks=[TQDMProgressBar(refresh_rate=20)],
    )

    # Train the model ⚡
    trainer.fit(mnist_model, train_loader)
```

</div>

## Define a workflow

Define the corresponding workflow as a YAML file in the `.dstack/workflows` folder within the repo to run it
via `dstack`.

<div editor-title=".dstack/workflows/mnist.yaml"> 

```yaml
workflows:
  - name: train-mnist
    provider: bash
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - python examples/mnist/train_mnist.py
    artifacts:
      - path: ./lightning_logs
```

</div>

The workflow instructs `dstack` how to execute it, which folders to save as artifacts for later use, which folders to cache between
runs, the dependencies it has on other workflows, the ports to open, and so on.

!!! info "NOTE:"
    `dstack` uses your local Python version by default to run workflows, but you can override it
    in [YAML](docs/reference/providers/bash.md).

## Run locally

Before you can run the workflow, make sure the changes are staged in Git.

<div class="termy">

```shell
$ git add --all
```

</div>

You can now run the workflow locally.

<div class="termy">

```shell
$ dstack run train-mnist

RUN      WORKFLOW     SUBMITTED  STATUS     TAG  BACKEND
zebra-1  train-mnist  now        Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

GPU available: False, used: False

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
---> 100%
```

</div>

!!! info "NOTE:"
    To run workflows locally, you need to have either Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    installed on your machine.

### Check status

Check recent runs status using the [`dstack ps`](docs/reference/cli/ps.md) command.

<div class="termy">

```shell
$ dstack ps

RUN      WORKFLOW     SUBMITTED  STATUS     TAG  BACKEND
zebra-1  train-mnist  now        Submitted       local
```

</div>

This command displays either the currently running workflows or the last completed run.
Use `dstack ps -a` to see all runs.

### List artifacts

To list artifacts from a run, use the [`dstack ls`](docs/reference/cli/ls.md) command.

<div class="termy">

```shell
$ dstack ls zebra-1

PATH             FILE        SIZE  BACKENDS
lightning_logs/  version_0/        local
```

</div>

!!! info "NOTE:"
    When you run a workflow locally, artifacts are stored in `~/.dstack/artifacts` and can only be reused by workflows that 
    also run locally.

## Configure the remote

To run workflows remotely (e.g. in a configured cloud account), you can configure a remote using
the [`dstack config`](docs/reference/cli/config.md) command.

See [Setup](docs/installation/index.md#configure-a-remote) to learn more about supported remote types and how to configure them.

## Run remotely

Use the `--remote` flag with `dstack run` to run the workflow remotely.

When running remotely, you can utilize the [`resources`](docs/usage/resources.md) feature to request hardware resources like GPUs, memory, or interruptible instances.

<div class="termy">

```shell
$ dstack run train-mnist --remote --gpu 1

RUN       WORKFLOW     SUBMITTED  STATUS     TAG  BACKEND
turtle-1  train-mnist  now        Submitted       aws

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

GPU available: True, used: True

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
---> 100%
```

</div>

When you run a workflow remotely, `dstack` automatically creates the necessary infrastructure within the
configured cloud account, runs the workflow, and stores the artifacts and destroys the
infrastructure upon completion.

!!! info "NOTE:"
    You can specify hardware resource requirements (like GPU, memory, interruptible instances, etc.) 
    for each remote workflow using [`resources`](docs/usage/resources.md).
