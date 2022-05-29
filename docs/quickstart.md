# Quickstart

This quickstart guide will introduce you to the key concepts and help you with the first steps of using dstack.

## Prerequisites

To complete this quickstart guide, ensure the following:

* You've [signed up](https://dstack.ai/signup) with dstack
* You have an existing AWS account (otherwise, [sign up](https://portal.aws.amazon.com/billing/signup) for AWS beforehand)
* You have Git installed locally
* You have Python 3.7 (or higher) and pip installed locally 

## Step 1: Link your AWS account

To let dstack provision infrastructure for running workflows in your cloud account, you have to provide
dstack the corresponding credentials. To do that, go to the `Settings`, and then `AWS`.

Here, provide `AWS Access Key ID` and `AWS Secret Access Key` that have the
[corresponding](runners.md#on-demand-runners) permissions to create EC2 instances in your AWS account.

Once you've specified credentials, use the `Add limit` button to configure limits:

![](images/dstack_on_demand_settings.png){ lazy=true width="1060" }

The `Limits` instruct dstack about the maximum number of EC2 instances of the specific `Instance Type` and in the specific `Region`, that
dstack can create at one time.

## Step 2: Install the CLI

To run workflows, you need the dstack CLI. Here's how to install and configure it:

```bash
pip install dstack -U
dstack config --token <token> 
```

Your token value can be found in `Settings`:

![](images/dstack_quickstart_token.png){ lazy=true width="1060" }

## Step 3: Clone the repo

In this quickstart guide, we'll use the 
[`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples) GitHub repo. Go ahead and clone this 
repo. Feel free to use the Terminal or open the repo wth your favourite IDE.

```bash
git clone https://github.com/dstackai/dstack-examples.git
cd dstack-examples
```

Workflows are defined in the `.dstack/workflows.yaml` file within the repo folder. If you open it, you'll see
the following content:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: download
        provider: python
        script: download.py
        requirements: requirements.txt
        artifacts:
          - data

      - name: train
        provider: python
        script: train.py
        requirements: requirements.txt
        depends-on:
          - download:latest
        artifacts:
          - model
        resources:
          gpu: 1
    ```

The first workflow is `download`. It downloads the [MNIST](http://yann.lecun.com/exdb/mnist/) dataset
to the folder `data` and saves it as an artifact.

Once you run this workflow, you'll be able to assign a tag to that run, and reuse its output artifacts
in other workflows, e.g. the `train` workflow.

## Step 4: Run the download workflow

Let's go ahead and run the `download` workflow. You can do it with the CLI:

```bash
dstack run download
```

!!! info ""
    Make sure you run the CLI from the repo directory.    

After you run any workflow, dstack needs a while to provision the required infrastructure to run it. 
You can watch the progress of your run, e.g. via the user interface.

If you see your run failed, make sure to check the logs of your run to find our the reason. Once the problem 
is fixed, feel free to run it again.

## Step 5: Assign a tag

In order to use the output artifacts of our run in other workflows, we need to assign a tag to our finished run, e.g.
via the user interface.

Because our `train` workflow refers to the `latest` tag in its `depends-on` clause, go ahead and assign the `latest`
tag to our finished `download` workflow.

## Step 6. Run the train workflow

Now that the finished `download` workflow is tagged with `latest`, everything is ready to run the `train` workflow.

One little thing before we do it. You may have noticed that in addition to `workflows.yaml`, the `dstack` folder
also contains a `.variables.yaml` file. This file can be used to define variables:

=== ".dstack/variables.yaml"
    ```yaml
    variables:
     train:
       batch-size: 64
       test-batch-size: 1000
       epochs: 1
       lr: 1.0
       gamma: 0.7
       seed: 1
       log-interval: 10
    ```

When you run a workflow, dstack passes its variables to the workflow script.

Inside your script, you can read them from environment variables:

```python
batch_size = os.environ.get("BATCH_SIZE")
```

When you run a workflow via the CLI, you can override any of workflow variables.

Let's fo ahead and run the `train` workflow:

```bash
dstack run train --epoch 100 --seed 2
```

When we run a workflow, dstack automatically provisions the required infrastructure.
You can edit the `resources` property to change requirements:

```yaml
resources:
  memory: 256GB
  gpu: 4
```

## Steps 7. Download artifacts

As a workflow is running, its output artifacts are saved in real-time.
You can browse its output artifacts via the user interface or the CLI.

To download the artifacts locally, use the following CLI command:

```bash
dstack artifacts download <run-name>
```