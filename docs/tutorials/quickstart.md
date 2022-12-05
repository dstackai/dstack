# Quickstart

Make sure you've [configured](../installation.md) the `dstack` CLI.

## Clone repo

In this tutorial, we'll use the 
[`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples) GitHub repo. Go ahead and clone this 
repo.

```shell
git clone https://github.com/dstackai/dstack-examples.git
cd dstack-examples
```

If you open the `.dstack/workflows/mnist.yaml` file inside the project, you'll see the following:

```yaml
workflows:
  - name: mnist-download
    provider: bash
    commands:
      - pip install -r requirements.txt
      - python mnist/download.py
    artifacts:
      - path: ./data

  - name: mnist-train
    deps:
      - tag: mnist_data
    provider: bash
    commands:
      - pip install -r requirements.txt
      - python mnist/train.py
    artifacts:
      - path: ./lightning_logs
```

The `mnist-download` workflow downloads the dataset to the `data` folder and saves it as an artifact.

The `mnist-train` workflow uses the data from the `mnist_data` tag to train a model. 

It writes checkpoints and logs within the `lightning_logs` folder, and saves it as an artifact.

## Init repo

Before you can use `dstack` on a new Git repo, you have to run the `dstack init` command:

```shell
dstack init
```

It will ensure that `dstack` has the access to the Git repo.

## Run download workflow

Now, you can use the [`dstack run`](../reference/cli/index.md#dstack-run) command to run the `mnist-download` workflow:

```shell
dstack run mnist-download
```

When you run a workflow, the CLI provisions infrastructure, prepares environment, fetches your code,
etc.

You'll see the output in real-time as your workflow is running.

```
RUN             WORKFLOW        SUBMITTED  OWNER           STATUS     TAG 
grumpy-zebra-1  mnist-download  now        peterschmidt85  Submitted  
 
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

!!! info "NOTE:"
    If you want `dstack` to run your workflow locally (instead of provisioning infrastructure in the cloud),
    use the `--local` argument (or `-l` for shorter).

    ```bash
    dstack run mnist-download -l
    ```

    Running workflows locally requires Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    to be installed locally.

Use the [`dstack ps`](../reference/cli/index.md#dstack-ps) command to see the status of recent workflows.

```shell
dstack ps
```

It shows currently running workflows or the last finished one. 

```shell
RUN             WORKFLOW        SUBMITTED  OWNER           STATUS  TAG 
grumpy-zebra-1  mnist-download  a min ago  peterschmidt85  Done    
```

To see all workflows, use the `dstack ps -a` command. 

!!! tip "NOTE:"
    The value in the `RUN` column is the name of the corresponding run. It serves as a unique identifier of the run.

## Access artifacts

To see artifacts of a run, use the
[`dstack artifacts list`](../reference/cli/index.md#dstack-artifacts-list) command followed
by the name of the run.

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

## Add tag

If you want to use the artifacts of a particular run from other workflows, you
can add a tag to this run.

Let's assign the `mnist_data` tag to our finished run `grumpy-zebra-1`.

```shell
dstack tags add mnist_data grumpy-zebra-1
```

You can see all tags of the current repo via the `dstack tags` command.

[//]: # (Note, tag names within on Git repo must be unique.)

You can use a tag name instead of the run name with the `dstack artifacts` command. 
Just put a colon before the tag name:

```shell
dstack artifacts list :mnist_data
```

## Run train workflow

Now that the `mnist_data` tag is added, we can run the `mnist-train` workflow.

```shell
dstack run mnist-train
```

On the start of the `mnist-train` workflow, dstack will download the artifacts of the tag `mnist_data` to the working directory.

```shell
RUN            WORKFLOW     SUBMITTED  OWNER           STATUS     TAG 
wet-mangust-2  mnist-train  now        peterschmidt85  Submitted  

Povisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Epoch 4: 100%|██████████████| 1876/1876 [00:17<00:00, 107.85it/s, loss=0.0944, v_num=0, val_loss=0.108, val_acc=0.968]
`Trainer.fit` stopped: `max_epochs=5` reached. 
Testing DataLoader 0: 100%|██████████████| 313/313 [00:00<00:00, 589.34it/s]

Test metric   DataLoader 0
val_acc       0.965399980545044
val_loss      0.10975822806358337
```

## Download artifacts

Once the `mnist-train` workflow is finished, if you want, you can download its artifacts using 
the [`dstack artifacts download`](../reference/cli/index.md#dstack-artifacts-download) command.

```shell
dstack artifacts download wet-mangust-2 .
```

It will download the `lightning_logs` folder to the current directory.