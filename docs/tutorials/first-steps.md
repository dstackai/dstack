# First steps

Before following the tutorial, make sure the `dstack` CLI is [installed and configured](../installation.md).

## Clone repo

In this tutorial, we'll use the 
[`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples) GitHub repo. Go ahead and clone this 
repo.

```shell
git clone https://github.com/dstackai/dstack-examples.git
cd dstack-examples
```

If you open the `.dstack/workflows.yaml` file inside the project, you'll see the following:

```yaml
workflows:
  - name: download
    provider: bash
    commands:
      - pip install -r requirements.txt
      - python mnist/download.py
    artifacts:
      - path: data

  - name: train
    deps:
      - tag: mnist_data
    provider: bash
    commands:
      - pip install -r requirements.txt
      - python mnist/train.py
    artifacts:
      - path: lightning_logs
```

The `download` workflow downloads the dataset to the `data` folder and saves it as an artifact.

The `train` workflow uses the data from the `mnist_data` tag to train a model. 

It writes checkpoints and logs within the `lightning_logs` folder, and saves it as an artifact.

## Init repo

Before you can use `dstack` on a new Git repo, you have to run the `dstack init` command:

```shell
dstack init
```

It will ensure that `dstack` has the access to the Git repo.

## Run download workflow

Now, you can use the [`dstack run`](../reference/cli/run.md) command to run the `download` workflow:

```shell
dstack run download
```

When you run a workflow, the CLI provisions infrastructure, prepares environment, fetches your code,
etc.

You'll see the output in real-time as your workflow is running.

```
RUN             TARGET    STATUS     APPS  ARTIFACTS  SUBMITTED  TAG 
grumpy-zebra-1  download  Submitted        data       now 
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Downloading http://yann.lecun.com/exdb/mnist/train-images-idx3-ubyte.gz
Extracting /workflow/data/MNIST/raw/train-images-idx3-ubyte.gz

Downloading http://yann.lecun.com/exdb/mnist/train-labels-idx1-ubyte.gz
Extracting /workflow/data/MNIST/raw/train-images-idx1-ubyte.gz

Downloading http://yann.lecun.com/exdb/mnist/train-labels-idx2-ubyte.gz
Extracting /workflow/data/MNIST/raw/train-images-idx2-ubyte.gz
```

Once the workflow is finished, its artifacts are saved and infrastructure is torn down.

You can see currently running or recently finished workflows, 
use the [`dstack ps`](../reference/cli/ps.md) command.

## Access artifacts

To see artifacts of a run, use the
[`dstack artifacts list`](../reference/cli/artifacts.md#artifacts-list) command followed
by its name:

```shell
dstack artifacts list grumpy-zebra-1
```

It will list all saved files inside artifacts along with their size:

```shell
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

To download artifacts, use the [`dstack artifacts download`](../reference/cli/artifacts.md#artifacts-download)
command:

```shell
dstack artifacts download grumpy-zebra-1
```

## Add tag

To use the artifacts of one workflow from another workflow, you have to add a tag to
the corresponding run:

Let's assign the `mnist_data` tag to our finished run `grumpy-zebra-1`.

```shell
dstack tags add mnist_data grumpy-zebra-1
```

[//]: # (Note, tag names within on Git repo must be unique.)

You can use a tag name instead of the run name with the `dstack artifacts` command. 
Just put a colon before the tag name:

```shell
dstack artifacts list :mnist_data
```

## Run train workflow

Now that the `mnist_data` tag is created, we can run the `train` workflow.

```shell
dstack run train
```

When you run the `train` workflow, before starting the workflow, `dstack` will download the artifacts of the tag `mnist_data`).
Then, you'll see the output in real-time.

```shell
Povisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Epoch 4: 100%|██████████████| 1876/1876 [00:17<00:00, 107.85it/s, loss=0.0944, v_num=0, val_loss=0.108, val_acc=0.968]
`Trainer.fit` stopped: `max_epochs=5` reached. 
Testing DataLoader 0: 100%|██████████████| 313/313 [00:00<00:00, 589.34it/s]

Test metric   DataLoader 0
val_acc       0.965399980545044
val_loss      0.10975822806358337
```

Once the `train` workflow is finished, you'll be able to access its artifacts.