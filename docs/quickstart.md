# Quickstart

This tutorial will walk you through the first steps of using dstack.

## Install the CLI

To use dstack, you'll only need the dstack CLI. No other software needs to be installed or deployed.

The dstack CLI will use your local cloud credentials (e.g. the default AWS environment variables 
or the credentials from `~/.aws/credentials`.)

The easiest way to install the dstack CLI is through pip:

```shell
pip install dstack
```

## Configure the backend

Before you can use dstack, you have to configure the dstack backend:

 * In which S3 bucket to store the state and the artifacts
 * In what region, create cloud instances.

To configure this, run the following command:

```shell
dstack config
```

The configuration will be stored in `~/.dstack/config.yaml`:

```yaml
backend: aws
bucket: "my-dstack-workspace"
region: "eu-west-1"
```

!!! info "NOTE:"
    AWS requires all S3 buckets to be unique across all users. Please make sure to choose a unique name.

## Clone the repo

In this tutorial, we'll use the 
[`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples) GitHub repo. Go ahead and clone this 
repo.

```shell
git clone https://github.com/dstackai/dstack-examples.git
cd dstack-examples
```

If you open the `.dstack/workflows.yaml` file, you'll see the following content:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: download
        help: "Download the MNIST dataset"
        provider: bash
        python: 3.10
        env:
          - PYTHONPATH=mnist
        commands:
          - pip install -r requirements.txt
          - python mnist/download.py
        artifacts:
          - data
    
      - name: train
        help: "Train a MNIST model"
        deps:
          - :mnist_data
        provider: bash
        requirements: "requirements.txt"
        env:
          - PYTHONPATH=mnist
        commands:
          - pip install -r requirements.txt
          - python mnist/train.py
        artifacts:
          - lightning_logs
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

This command will ensure that dstack has the access to the repo.

## Run the download workflow

Let's go ahead and run the `download` workflow via the CLI:

```shell
dstack run download

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

...
```

!!! info "NOTE:"
    Make sure to always run the CLI from the project repository directory.

Once you run the workflow, dstack will create the required cloud instance within a minute,
and will run your workflow. You'll see the output in real-time as your 
workflow is running.

!!! tip "NOTE:"
    As long as your project is under Git, you don't have to commit local changes before using the run command.
    dstack will take the local changes into account automatically.
    Just make sure that these changes are staged (using the `git add` command).

## Access the run artifacts

If the run has finished successfully, you can see its output artifacts using 
the `dstack artifacts list command and the name of the run:

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

To download artifacts, use a similar command followed by the path, where to download the artifacts:

```shell
dstack artifacts download <run-name> .
```

## Add a tag

Now, to use the artifacts from other workflows, we need to assign a tag to it, e.g. `mnist_data`.

It can be done the following way:

```shell
dstack tags add mnist_data <run-name>
```

!!! info "NOTE:"
    All tags within the same project repository must be unique.

You can access the artifacts of a tag the same way as for a run, except that you have to prepend the name of the tag
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

## Stop and restart the workflow

You can stop the `train` workflow using the `dstack stop` command followed by the name of the run.

By default, output artifacts are stored in real-time. This means, if the workflow saves the checkpoints while it's 
running, you'll be able to restart the workflow using the `dstack restart` command and the workflow will
start from where it was interrupted.

## Change resource requirements

If you don't specify resource requirements for your workflow, by default, when you run it, dstack uses the 
minimal instance type.

To specify resource requirements for your workflow, add the `resources` property to it in `.dstack/workflows.yaml`.

For example, if you want to use one GPU for the `train` workflows, you'll have to modify the `.dstack/workflows.yaml`
file, this way:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: download
        help: "Download the MNIST dataset"
        provider: bash
        python: 3.10
        env:
          - PYTHONPATH=mnist
        commands:
          - pip install -r requirements.txt
          - python mnist/download.py
        artifacts:
          - data
    
      - name: train
        help: "Train a MNIST model"
        deps:
          - :mnist_data
        provider: bash
        requirements: "requirements.txt"
        env:
          - PYTHONPATH=mnist
        commands:
          - pip install -r requirements.txt
          - python mnist/train.py
        artifacts:
          - lightning_logs
        resources:
            gpu: 1
    ```

The `resources` property allows you to specify the number of CPUs, GPUs, the name of the GPU (e.g. `V80` or `V100`),
the amount of memory, and even whether you want to use spot/preemptive instances or regular ones.
Find more details on how to specify resources in the `bash` provider [documentation](workflows/bash.md#resources).

## More CLI commands

The other useful CLI commands include:

 - `dstack status` – Show status of runs within the current project. By default, shows the unfinished runs only, or the 
  last finished run. Use `dstack status -a` to see all recent runs.
 - `dstack tags` – List existing tags within the current project.
 - `dstack secrets` – Manages secrets. Secrets can be used to access sensitive data (passwords, tokens, etc)
  from workflows without hard-coding it within the code.
 - `dstack delete` – Deletes runs within the current project. To delete all runs, use the `dstack delete -a` 
  command. Deleting runs doesn't affect tags. Feel free to delete the run after you've assigned a tag to it.

For more details on the CLI commands, check out the CLI [documentation](cli/index.md).