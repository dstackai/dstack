# Quickstart

This tutorial will walk you through the first steps of using dstack.

!!! info "NOTE:"
    Make sure you've [installed and configured the dstack CLI](installation.md) before following this tutorial.

## Clone the repo

In this tutorial, we'll use the 
[`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples) GitHub repo. Go ahead and clone this 
repo.

```shell
git clone https://github.com/dstackai/dstack-examples.git
cd dstack-examples
```

If you open the `.dstack/workflows.yaml` file inside the project directory, you'll see the following content:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: download
        help: "Download the MNIST dataset"
        provider: bash
        commands:
          - pip install -r requirements.txt
          - python mnist/download.py
        artifacts:
          - path: data
    
      - name: train
        help: "Train a MNIST model"
        deps:
          - tag: mnist_data
        provider: bash
        commands:
          - pip install -r requirements.txt
          - python mnist/train.py
        artifacts:
          - path: lightning_logs
    ```

The `download` workflow downloads the [MNIST](http://yann.lecun.com/exdb/mnist/) dataset
to the `data` folder and saves it as an artifact.

If you run this workflow, you'll be able to assign a tag to that run (e.g. the tag `mnist_data`), and reuse its output artifacts
in other workflows via that tag, e.g. the `train` workflow.

The `train` workflow uses the data from the `mnist_data` tag to train a model. It saves the checkpoints and logs
within the `lightning_logs` folder.

## Init the repo

Before you can use dstack with the new repo, you have to initialize it using the following command:

```shell
dstack init
```

This command will ensure that dstack has the access to the Git repository.

## Run the download workflow

Let's go ahead and run the `download` workflow via the [`dstack run`](reference/cli/run.md) CLI command:

```shell
dstack run download

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

...
```

!!! info "NOTE:"
    Make sure to use the CLI from within a Git repository directory.
    When you run a workflow, dstack detects the current branch, commit hash, and local changes.

Once you run the workflow, dstack creates the required cloud instance(s) within a minute,
download the dependencies, and run your workflow. You'll see the output in real-time as your 
workflow is running.

!!! info "NOTE:"
    To see the list of currently running or recently finished workflows, use the [`dstack ps`](reference/cli/ps.md) command.

## Access the run artifacts

If the run has finished successfully, you can see its output artifacts using 
the [`dstack artifacts list`](reference/cli/artifacts.md#artifacts-list) CLI command with the
name of the run:

```shell
dstack artifacts list <run-name>

 ARTIFACT  FILE                                  SIZE
 data      MNIST/raw/t10k-images-idx3-ubyte      7.5MiB
           MNIST/raw/t10k-images-idx3-ubyte.gz   1.6MiB
           MNIST/raw/t10k-labels-idx1-ubyte      9.8KiB
           MNIST/raw/t10k-labels-idx1-ubyte.gz   4.4KiB
           MNIST/raw/train-images-idx3-ubyte     44.9MiB
           MNIST/raw/train-images-idx3-ubyte.gz  9.5MiB
           MNIST/raw/train-labels-idx1-ubyte     58.6KiB
           MNIST/raw/train-labels-idx1-ubyte.gz  28.2KiB
```

To download artifacts, use the [`dstack artifacts download`](reference/cli/artifacts.md#artifacts-download) CLI command 
also with the name of the run and a path to the directory, where to download the artifacts:

```shell
dstack artifacts download <run-name> .
```

## Add a tag

Now, to use the artifacts from other workflows, we need to assign a tag to it, e.g. `mnist_data`.

It can be done via the [`dstack tags add`](reference/cli/tags.md#tags-add) CLI command:

```shell
dstack tags add mnist_data <run-name>
```

!!! info "NOTE:"
    All tags within the same project repository must be unique.

You can access the artifacts of a tag the same way as for a run. Just prepend the name of the tag
with a colon:  

```shell
dstack artifacts list :mnist_data

 ARTIFACT  FILE                                  SIZE
 data      MNIST/raw/t10k-images-idx3-ubyte      7.5MiB
           MNIST/raw/t10k-images-idx3-ubyte.gz   1.6MiB
           MNIST/raw/t10k-labels-idx1-ubyte      9.8KiB
           MNIST/raw/t10k-labels-idx1-ubyte.gz   4.4KiB
           MNIST/raw/train-images-idx3-ubyte     44.9MiB
           MNIST/raw/train-images-idx3-ubyte.gz  9.5MiB
           MNIST/raw/train-labels-idx1-ubyte     58.6KiB
           MNIST/raw/train-labels-idx1-ubyte.gz  28.2KiB
```

## Run the train workflow

Once the `mnist_data` tag is created, let's go ahead and run the `train` workflow:

```shell
dstack run train

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

...
```

The `train` workflow will use the data from the tag to train a model and will save the checkpoint to the output artifacts.

!!! info "NOTE:"
    What's next? Make sure to check out the [Examples](reference/examples/index.md), the [CLI](reference/cli/index.md), 
    [Workflows](reference/workflows/index.md) reference pages.  