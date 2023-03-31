# Quick start

This tutorial will guide you through using `dstack` locally and remotely, step by step.

!!! info "NOTE:"
    The source code of this tutorial is available in the [Playground](playground.md).  

## 1. Install the CLI

Use `pip` to install `dstack`:

<div class="termy">

```shell
$ pip install dstack --upgrade
```

</div>

## 2. Create a repo

To use `dstack`, your project must be managed by Git and have at least one remote branch configured.
Your repository can be hosted on GitHub, GitLab, BitBucket, or any other platform.

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

### Init the repo

Once you've set up a remote branch in your repo, go ahead and run this command:

<div class="termy">

```shell
$ dstack init
```

</div>

It will set up the repo to work with `dstack`.

Now that everything is in place, you can use `dstack` with your project.

## 3. Prepare data

Let us begin by creating a Python script that will prepare the data for our training script.

### Create a Python script

Let us create the following Python script:

<div editor-title="tutorials/mnist/mnist_data.py"> 

```python
from torchvision.datasets import MNIST

if __name__ == '__main__':
    # Download train data
    MNIST("./data", train=True, download=True)
    # Download test data
    MNIST("./data", train=False, download=True)
```

</div>

This script downloads the MNIST dataset and saves it locally to the `data` folder.

To run the script via `dstack`, it must be defined as a workflow in a YAML file in the
`.dstack/workflows` folder within the repo. 

### Create a workflow YAML file

Define the `mnist-data` workflow by creating the following YAML file:

<div editor-title=".dstack/workflows/mnist.yaml"> 

```yaml
workflows:
  - name: mnist-data
    provider: bash
    commands:
      - pip install torchvision
      - python tutorials/mnist/mnist_data.py
    artifacts:
      - path: ./data
```

</div>

!!! info "NOTE:"
    In order for the files to be available in a workflow, they have to be tracked by Git.
    To ensure Git tracks the files, run:

    <div class="termy">

    ```shell
    $ git add .dstack tutorials
    ```

    </div>

    After that, `dstack` will keep track of the file changes automatically, so you don't have to run `git add` on every change.

### Run the workflow locally

Now you can run the defined workflow using the `dstack run` command:

<div class="termy">

```shell
$ dstack run mnist-data

RUN             WORKFLOW    SUBMITTED  STATUS     TAG  BACKEND
zebra-1         mnist-data  now        Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Downloading http://yann.lecun.com/exdb/mnist/train-images-idx3-ubyte.gz
---> 100%

$
```

</div>

!!! info "NOTE:"
    By default, `dstack` runs workflows locally, which requires having either Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    installed locally.

!!! info "NOTE:"
    By default, `dstack` uses the same Python version to run workflows as your local Python version.
    If you use Python 3.11, the `mnist-data` workflow will fail since it's not yet supported by `torchvision`.
    To solve such problems, `dstack` allows you to specify a Python version for the workflow with the `python` parameter in the YAML file, e.g. `python: 3.9`.

### Check status

To check the status of recent runs, use the [`dstack ps`](reference/cli/ps.md) command:

<div class="termy">

```shell
$ dstack ps

RUN      WORKFLOW    SUBMITTED  STATUS     TAG  BACKEND
zebra-1  mnist-data  now        Submitted       local
```

</div>

This command displays either the currently running workflows or the last completed run.
To see all runs, use the `dstack ps -a` command.

### List artifacts

Once a run is finished, its artifacts are saved and can be reused.

You can list artifacts of any run using the [`dstack ls`](reference/cli/ls.md) command:

<div class="termy">

```shell
$ dstack ls zebra-1

PATH  FILE                                  SIZE
data  MNIST/raw/t10k-images-idx3-ubyte      7.5MiB
      MNIST/raw/t10k-images-idx3-ubyte.gz   1.6MiB
      MNIST/raw/t10k-labels-idx1-ubyte      9.8KiB
      MNIST/raw/t10k-labels-idx1-ubyte.gz   4.4KiB
      MNIST/raw/train-images-idx3-ubyte     44.9MiB
      MNIST/raw/train-images-idx3-ubyte.gz  9.5MiB
      MNIST/raw/train-labels-idx1-ubyte     58.6KiB
      MNIST/raw/train-labels-idx1-ubyte.gz  28.2KiB
```

</div>

This will display all the files and their sizes.

## 4. Train a model

Now, that the data is prepared, let's create a Python script to train a model.

### Create a Python script

Let us create the following training script:

<div editor-title="tutorials/mnist/train_mnist.py"> 

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


BATCH_SIZE = 256 if torch.cuda.is_available() else 64

if __name__ == "__main__":
    # Init our model
    mnist_model = MNISTModel()

    # Init DataLoader from MNIST Dataset
    train_ds = MNIST("./data", train=True, download=False, transform=transforms.ToTensor())
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE)

    # Initialize a trainer
    trainer = Trainer(
        accelerator="auto",
        devices=1 if torch.cuda.is_available() else None,  # limiting got iPython runs
        max_epochs=3,
        callbacks=[TQDMProgressBar(refresh_rate=20)],
    )

    # Train the model ⚡
    trainer.fit(mnist_model, train_loader)
```

</div>

This script trains a model using the MNIST dataset from the local `data` folder.

### Update the workflow YAML file

Ddd the `train-mnist` workflow to the workflow YAML file:

<div editor-title=".dstack/workflows/mnist.yaml"> 

```yaml
workflows:
  - name: mnist-data
    provider: bash
    commands:
      - pip install torchvision
      - python tutorials/mnist/mnist_data.py
    artifacts:
      - path: ./data
        
  - name: train-mnist
    provider: bash
    deps:
      - workflow: mnist-data 
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - python tutorials/mnist/train_mnist.py
    artifacts:
      - path: ./lightning_logs
```

</div>

To reuse data across workflows, we made the `train-mnist` workflow dependent on the `mnist-data` workflow.
When we run `train-mnist`, `dstack` will automatically put the data from the last `mnist-data` run in the `data` folder.

### Run the workflow locally

Now you can run the defined workflow using the `dstack run` command:

<div class="termy">

```shell
$ dstack run train-mnist

RUN        WORKFLOW     SUBMITTED  STATUS     TAG 
mangust-2  train-mnist  now        Submitted  

Povisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
---> 100%

$
```

</div>

## 5. Configure the remote

When you run a workflow locally, artifacts are stored in `~/.dstack/artifacts` and can only be reused by workflows that 
also run locally.

To run workflows remotely or enable artifact reuse outside of your machine, you can configure a remote 
using the [`dstack config`](reference/cli/config.md) command.

See [Installation](installation.md#configure-a-remote) to learn more about supported remote types and how to configure them.

## 6. Push artifacts

To reuse the artifacts of the `mnist-data` workflow outside your machine, you can use the `dstack push` command to
upload them to the configured remote (e.g. the cloud).

<div class="termy">

```shell
$ dstack push zebra-1
```

</div>

!!! info "NOTE:"
    When you run a workflow remotely, its artifacts are pushed automatically, and it is much faster 
    compared to a pushing a local run.

    Therefore, if your goal is to reuse the `mnist-data` artifacts remotely, it is more convenient to run 
    the `mnist-data` workflow remotely in the first place.

## 7. Train a model remotely

!!! info "NOTE:"
    Before running the `mnist-train` workflow remotely, we have to ensure that the `mnist-data` artifacts are available remotely.

    Either follow the previous step of pushing the artifacts, or run the `mnist-data` workflow remotely:

    ```shell
    dstack run mnist-data --remote
    ```

Now we can run the `train-mnist` workflow remotely (e.g. in the configured cloud):

<div class="termy">

```shell
$ dstack run train-mnist --remote
```

</div>

When you run a workflow remotely, `dstack` automatically creates the necessary infrastructure within the
configured cloud account, runs the workflow, and stores the artifacts and destroys the
infrastructure upon completion.

!!! info "NOTE:"
    You can specify hardware resource requirements (like GPU, memory, interruptible instances, etc.) 
    for each remote workflow using [`resources`](usage/remotes.md#resources).
