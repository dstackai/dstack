# Quickstart

## Introduction

This tutorial teaches you dstack essentials such as workflows, runs, jobs, artifacts, and runners.

To complete this tutorial, you'll need a [dstack.ai](https://dstack.ai) account.

## Set up runners

Runners are machines that run submitted workflows. dstack supports two types of runners: the `on-demand` runners and `self-hosted` runners. 

Thee `on-demand` are runners created automatically by dstack (in the user's 
cloud account) for the time of running workflows. The `self-hosted` runners are set up manually to run workflows
using the user's own hardware.

### Option 1: Set up on-demand runners

To use the `on-demand` runners, go to the `Settings`, then `AWS`.

Here, you have to provide `AWS Access Key ID` and `AWS Secret Access Key` that have the
[corresponding](on-demand-runners.md#aws-credentials) permissions to create EC2 instances in you AWS account.

Once you've provided credentials, use the `Add limit` button to configure limits:

![](images/dstack_on_demand_settings.png){ lazy=true width="1060" }

The configured limits represent the maximum number of EC2 instances of the specific type and in the specific region, that
dstack can create at one time to run workflows.

### Option 2: Set up self-hosted runners

As an alternative to `on-demand` runners, you can run workflows on your own hardware. 

To do that, you have to run the following command on your server:

```bash
curl -fsSL https://get.dstack.ai/runner -o get-dstack-runner.sh
sudo sh get-dstack-runner.sh
dstack-runner config --token <token>
dstack-runner start
```

The `token` value can be found in `Settings`:

![](images/dstack_quickstart_token.png){ lazy=true width="1060" }

If you've done this step properly, you'll see your server on the `Runners` page:

![](images/dstack_quickstart_runners.png){ lazy=true width="1060" }

## Install the CLI

Now, to be able to run and manage workflows interactively, install the dstack CLI.

```bash
pip install dstack -U
dstack config --token <token> 
```

## Clone the repository

In this tutorial, we'll run workflows defined in 
[`github.com/dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples).

```bash
git clone https://github.com/dstackai/dstack-examples.git
cd dstack-examples
```

This project includes two workflows: `download-mnist` and `train-mnist`. The frst workflow downloads the [MNIST](http://yann.lecun.com/exdb/mnist/) dataset,
whilst the second workflow trains a model using the output of the first workflow as an input:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: download-mnist
        provider: python
        requirements: requirements.txt
        python_script: download.py
        artifacts:
          - data
    
      - name: train-mnist
        provider: python
        requirements: requirements.txt
        python_script: train.py
        artifacts:
          - model
        depends-on:
          - download-mnist
        resources:
          gpu: ${{ gpu }}     
    ```

=== ".dstack/variables.yaml"

    ```yaml
    variables:
     train-mnist:
       gpu: 1
       batch-size: 64
       test-batch-size: 1000
       epochs: 1
       lr: 1.0
       gamma: 0.7
       seed: 1
       log-interval: 10
    ```

## Run workflows

Go ahead, and run the `train-mnist` workflow using the following command:

```bash
dstack run train-mnist 
```

If you want to change any of the variables, you can do that in `.dstack/variables.yaml`, or from the CLI:

```bash
dstack run train-mnist --gpu 2 --epoch 100 --seed 2
```

When you run `train-mnist`, because `train-mnist` depends on `download-mnist`, dstack will create a run with two jobs: 
one for `train-mnist` and one for `download-mnist`:

![](images/dstack_quickstart_runs.png){ lazy=true width="1060" }

## Tag runs

When the run is finished, you can assign a tag to it, e.g. `latest`:

```bash
dstack tag cowardly-goose-1 latest
```

Now, you can refer to this tagged workflow from `.dstack/workflows.yaml`:

```yaml
   workflows:
     - name: download-mnist
       provider: python
       requirements: requirements.txt
       python_script: download.py
       artifacts:
         - data

     - name: train-mnist
       provider: python
       requirements: requirements.txt
       python_script: train.py
       artifacts:
         - model
       depends-on:
         - download-mnist:latest
       resources:
         gpu: 1     
```

Now, if you run the `train-mnist` workflow, dstack won't create a job for the `download-mnist` workflow.
Instead, it will use the artifacts of the tagged workflow.

!!! info ""
    Keep in mind that you can tag as many runs as you want. When you refer to a workflow via its tag, 
    dstack will use the job that has the corresponding tag, workflow name, and variables.

!!! warning "Don't have an AWS account or your own hardware?"
    First, if you'd like to use dstack with other cloud vendors, please upvote the corresponding requests:
    [GCP](https://github.com/dstackai/dstack/issues/1) and [Azure](https://github.com/dstackai/dstack/issues/2).

    If you'd like to use dstack with your existing Kubernetes cluster, upvote [this request](https://github.com/dstackai/dstack/issues/4).

    Finally, if you'd like dstack to manage infrastructure on its own so you can pay directly to dstack for computing 
    instances, please upvote [this request](https://github.com/dstackai/dstack/issues/3).

It's now time to give a try to dstack, and run your first workflow.

