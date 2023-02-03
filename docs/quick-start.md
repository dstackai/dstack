# Quick start

This tutorial will guide you through using `dstack` locally and remotely, step by step.

## 1. Install the CLI

Use `pip`, to install the CLI:

```shell hl_lines="1"
pip install dstack --upgrade
```

## 2. Create a repo

To use `dstack`, your project must be managed by Git and have at least one remote branch configured.
Your repository can be hosted on GitHub, GitLab, BitBucket, or any other platform.

!!! info "NOTE:"
    If you haven't set up a remote branch in your repo yet, don't worry! Here's how you can do it:
    
    ```shell
    echo "# Quick start" >> README.md
    git init
    git add README.md
    git commit -m "first commit"
    git branch -M main
    git remote add origin "<your remote repo URL>"
    git push -u origin main
    ```

### Init the repo

Once you've set up a remote branch in your repo, go ahead and run this command:

```shell hl_lines="1"
dstack init
```

Now that everything is in place, you can use dstack with your project.

## 3. Prepare data

Let us begin by creating a Python script that will prepare the data for our training script.

### Create a Python script

Let us create the following `mnist/mnist_data.py` script: 

```python
from torchvision.datasets import MNIST

if __name__ == '__main__':
    # Download train data
    MNIST("./data", train=True, download=True)
    # Download test data
    MNIST("./data", train=False, download=True)
```

This script downloads the MNIST dataset and save it locally in the data folder.

To run it via `dstack`, it must be defined as a workflow in a YAML file in the
`.dstack/workflows` folder within the repo. 

### Create a workflow YAML file

Create the file `.dstack/workflows/mnist.yaml` and define the `mnist-data` workflow like this:

```yaml
workflows:
  - name: mnist-data
    provider: bash
    commands:
      - pip install torchvision
      - python mnist/mnist_data.py
    artifacts:
      - path: ./data
```

### Run the workflow locally

Now, you can run the defined workflow using the `dstack run` command:

```shell hl_lines="1"
dstack run mnist-data
```

!!! info "NOTE:"
    Although `dstack` tracks your code on every run, committing changes to the repository is not necessary. 
    You just need to ensure that your code changes are in the staging area. 
    Here's how to ensure it:

    ```shell hl_lines="1"
    git add .dstack mnist
    ```

As the workflow is running, you will see its output:

```shell hl_lines="1"
RUN             WORKFLOW    SUBMITTED  OWNER           STATUS     TAG  BACKEND
grumpy-zebra-1  mnist-data  now        peterschmidt85  Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Downloading http://yann.lecun.com/exdb/mnist/train-images-idx3-ubyte.gz
Extracting /workflow/data/MNIST/raw/train-images-idx3-ubyte.gz

Downloading http://yann.lecun.com/exdb/mnist/train-labels-idx1-ubyte.gz
Extracting /workflow/data/MNIST/raw/train-images-idx1-ubyte.gz

Downloading http://yann.lecun.com/exdb/mnist/train-labels-idx2-ubyte.gz
Extracting /workflow/data/MNIST/raw/train-images-idx2-ubyte.gz
```

!!! info "NOTE:"
    By default, `dstack` runs workflows locally, which requires having either Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    installed locally.

### Check status

To check the status of recent runs, use the [`dstack ps`](reference/cli/index.md#dstack-ps) command:

```shell hl_lines="1"
dstack ps
```

This command displays either the current running workflows or the last completed run:

```shell hl_lines="1"
RUN             WORKFLOW    SUBMITTED  OWNER           STATUS     TAG  BACKEND
grumpy-zebra-1  mnist-data  now        peterschmidt85  Submitted       local
```

To see all runs, use the `dstack ps -a` command.

### List artifacts

Once a run is finished, its artifacts are saved and can be reused.

You can list artifacts of any run using the [`dstack ls`](reference/cli/index.md#dstack-ls) command:

```shell hl_lines="1"
dstack ls grumpy-zebra-1
```

This will display all the files and their sizes:

```shell hl_lines="1"
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

## 4. Train a model

Now, that the data is prepared, let's create a Python script to train a model.

### Create a Python script

Let us create the following `mnist/train_mnist.py` script:

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

This script trains a model using the MNIST dataset from the local `data` folder.

### Update the workflow YAML file

Update the `.dstack/workflows/mnist.yaml` file to add the `train-mnist` workflow:

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

To reuse data across workflows, in the `train-mnist` workflow, we added a dependency on the `mnist-data` workflow .
When we run `train-mnist`, `dstack` will automatically put the data from the last `mnist-data` run in the `data` folder.

### Run the workflow locally

Now, you can run the defined workflow using the `dstack run` command:

```shell hl_lines="1"
dstack run train-mnist
```

!!! info "NOTE:"
    Double-check the changes are in the staging area again.

    ```shell hl_lines="1"
    git add mnist
    ```

As the workflow is running, you will see its output:

```shell hl_lines="1"
RUN            WORKFLOW     SUBMITTED  OWNER           STATUS     TAG 
wet-mangust-2  train-mnist  now        peterschmidt85  Submitted  

Povisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Epoch 2: 100%|██████████████| 1876/1876 [00:17<00:00, 107.85it/s, loss=0.0944, v_num=0, val_loss=0.108, val_acc=0.968]
`Trainer.fit` stopped: `max_epochs=3` reached. 
Testing DataLoader 0: 100%|██████████████| 313/313 [00:00<00:00, 589.34it/s]

Test metric   DataLoader 0
val_acc       0.965399980545044
val_loss      0.10975822806358337
```

## 5. Configure the remote

When you run a workflow locally, artifacts are stored in `~/.dstack/artifacts` and can only be reused by workflows that 
also run locally.

To run workflows remotely or enable artifact reuse outside of your machine, you must configure your remote settings
using the [`dstack config`](reference/cli/config.md) command.

```shell hl_lines="1"
dstack config
```

This command prompts you to select an AWS profile for credentials, an AWS region for workflow execution, and an S3
bucket to store remote artifacts and metadata.

```shell
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

## 6. Push artifacts

To reuse the artifacts of the `mnist-data` workflow outside of your machine, you can use the `dstack push` command to
upload them to the configured remote (e.g. the cloud).

```shell hl_lines="1"
dstack push grumpy-zebra-1
```

!!! info "NOTE:"
    When you run a workflow remotely, its artifacts are pushed automatically, and it is much faster 
    compared to a pushing a local run.

    Therefore, if your goal is to reuse the `mnist-data` artifacts remotely, it is more convenient to run 
    the `mnist-data` workflow remotely in the first hand.

## 7. Train a model remotely

!!! info "NOTE:"
    Before running the `mnist-train` workflow remotely, we have to ensure that the `mnist-data`  artifacts  
    are available remotely.

    Either follow the previous step of pushing the artifacts, or run the `mnist-data` workflow remotely:

    ```shell hl_lines="1"
    dstack run mnist-data --remote
    ```

Now, we can run the `train-mnist` workflow remotely (e.g. in the configured cloud):

```shell hl_lines="1"
dstack run train-mnist --remote
```

When you run a workflow remotely, `dstack` automatically creates the necessary infrastructure (within the
configured cloud account), runs the workflow, and upon completion, stores the artifacts and destroys the
infrastructure.

!!! info "NOTE:"
    You can specify hardware resource requirements (like GPU, memory, interruptible instances, etc.) 
    for each remote workflow using [`resources`](basics/resources.md).

And that's a wrap! If you need to refer to it, the source code for this tutorial can be found in our GitHub [repo](https://github.com/dstackai/dstack-examples).