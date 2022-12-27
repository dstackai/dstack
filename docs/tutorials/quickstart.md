# Quickstart

In this tutorial, we will learn how to use `dstack` to run ML workflows 
independently of the environment, and enable sharing of data and models within your team.

## Step 1: Clone repo

In this tutorial, we'll use the 
[`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples) GitHub repo. Go ahead and clone it:

```shell hl_lines="1-2"
git clone https://github.com/dstackai/dstack-examples.git
cd dstack-examples
```

If you open the `.dstack/workflows/mnist.yaml` file, you'll see the following:

```yaml
workflows:
  # Saves the MNIST dataset as reusable artifact for other workflows
  - name: mnist-data
    provider: bash
    commands:
      - pip install -r mnist/requirements.txt
      - python mnist/download.py
    artifacts:
      # Saves the folder with the dataset as an artifact
      - path: ./data

  # Trains a model using the dataset from the `mnist-data` workflow
  - name: mnist-train
    provider: bash
    deps:
      # Depends on the artifacts from the `mnist-data` workflow
      - workflow: mnist-data
    commands:
      - pip install -r mnist/requirements.txt
      - python mnist/train.py
    artifacts:
      # Saves the `folder with logs and checkpoints as an artifact
      - path: ./lightning_logs
```

!!! info "NOTE:"
    With workflows defined in this manner, `dstack` allows for effortless execution in any environment (whether locally 
    or remotely), while also enabling versioning and reuse of artifacts.
    
## Step 2: Init repo

If you haven't yet installed `dstack`, run this command:

```shell hl_lines="1"
pip install dstack --upgrade
```

Before using `dstack` on a new repo, run the `dstack init` command:

```shell hl_lines="1"
dstack init
```

## Step 3: Run mnist-data workflow locally

By default, `dstack` runs the workflow locally.

Let's go ahead and run the `mnist-data` workflow using the [`dstack run`](../reference/cli/index.md#dstack-run) command:

```shell hl_lines="1"
dstack run mnist-data
```

As the workflow is running, you will see its output:

```shell hl_lines="1"
RUN             WORKFLOW    SUBMITTED  OWNER           STATUS     TAG 
grumpy-zebra-1  mnist-data  now        peterschmidt85  Submitted  
 
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
    To run workflows locally, it is required to have either Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    pre-installed.

### Check status

To check the status of recent runs, use the [`dstack ps`](../reference/cli/index.md#dstack-ps) command:

```shell hl_lines="1"
dstack ps
```

This command displays either the current running workflows or the last completed run:

```shell hl_lines="1"
RUN             WORKFLOW    SUBMITTED  OWNER           STATUS  TAG 
grumpy-zebra-1  mnist-data  a min ago  peterschmidt85  Done    
```

To see all runs, use the `dstack ps -a` command.

!!! info "NOTE:"
    The `RUN` column contains the name of the run. Use this value in other CLI commands (e.g.
    [`dstack stop`](../reference/cli/index.md#dstack-stop), [`dstack artifacts`](../reference/cli/index.md#dstack-artifacts), etc.) to refer to the 
    corresponding run.

### List artifacts

Once a run is finished, its artifacts are saved and can be reused.

You can list artifacts of any run using the [`dstack ls`](../reference/cli/index.md#dstack-ls) command:

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

## Step 4: Run mnist-train workflow locally

Now, let's run the `mnist-train` workflow:

```shell hl_lines="1"
dstack run mnist-train
```

Because the `mnist-train` workflow depends on the `mnist-data` workflow,
it will reuse the artifacts from the most recent run of the `mnist-data` workflow.

```shell hl_lines="1"
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

!!! info "NOTE:"
    If necessary, `dstack` allows you to reuse artifacts from a specific run (rather than using the most recent run) 
    by using [tags](../examples/index.md#tags). However, this is beyond the scope of this tutorial.

## Step 5: Configure the remote

When you run a workflow locally, artifacts are stored in `~/.dstack/artifacts` and 
can be reused only from the workflows that run locally too.

To run workflows remotely (e.g. in the cloud) or enable reuse of the artifacts outside your machine, configure your
remote settings using the [`dstack config`](../reference/cli/index.md#dstack-config) command:

```shell hl_lines="1"
dstack config
```

This command will ask you to choose an AWS profile (which will be used for AWS credentials), an AWS region (where
workflows will be run), and an S3 bucket (to store remote artifacts and metadata):

```shell
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

## Step 5 (Optional): Push artifacts

If you'd like to reuse the artifacts of the `mnist-data` workflow outside your machine,
you must push these artifacts using the `dstack push` command:

```shell hl_lines="1"
dstack push grumpy-zebra-1
```

!!! info "NOTE:"
    If you run a workflow remotely, artifacts are pushed automatically, and it's typically 
    a lot faster than pushing artifacts of a local run.

    Therefore, if you plan to reuse the artifacts of the `mnist-data` workflow remotely, it's
    easier to run the `mnist-data` workflow remotely in the first place.

## Step 6: Run mnist-train remotely

!!! info "NOTE:"
    Before we run the `mnist-train` workflow remotely, we have to ensure that the artifacts of the `mnist-data` 
    workflow are available remotely.

    For this, either follow the previous step (pushing artifacts to the cloud), or run the `mnist-data` workflow in the cloud:

    ```shell hl_lines="1"
    dstack run mnist-data --remote
    ```

Now, let's run the `mnist-train` workflow in the cloud:

```shell hl_lines="1"
dstack run mnist-train --remote
```

When you run a workflow remotely, `dstack` automatically sets up the necessary infrastructure (e.g. within a 
configured cloud account), runs the workflow, and upon completion, saves the artifacts remotely and tears down 
the infrastructure.

!!! info "NOTE:"
    You can specify hardware resource requirements, such as the GPU, memory, and the use of interruptible instances, 
    for each remotely running workflow using [`resources`](../examples/index.md#resources). 
    However, this topic will not be addressed in this tutorial.

[//]: # (Consider introducing `remotes` and resources `profiles` - To be elaborated)

[//]: # (## Conclusion)

[//]: # (Reiterate on what is the main value of dstack)

[//]: # (Mention what is not covered)