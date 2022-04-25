# Quickstart

## Step 1: Set up runners

Runners are machines that run submitted workflows. dstack supports two types of runners: on-demand runners
and self-hosted runners. 

The on-demand runners are created automatically by dstack (in the computing vendor, configured by the user, e.g. AWS) 
for the time of running workflows. The self-hosted runners can be set up manually to run workflows
using the user's own hardware.

### Option 1: Set up on-demand runners

To use on-demand runners, go to the `Settings`, then `AWS`.

Here, you have to provide `AWS Access Key ID` and `AWS Secret Access Key` that have the
[corresponding](on-demand-runners.md#aws-credentials) permissions to create EC2 instances in your AWS account.

Once you've provided credentials, use the `Add limit` button to configure limits:

![](images/dstack_on_demand_settings.png){ lazy=true width="1060" }

The configured `Limits` represent the maximum number of EC2 instances of the specific `Instance Type` and in the specific `Region`, that
dstack can create at one time to run workflows.

### Option 2: Set up self-hosted runners

As an alternative to on-demand runners, you can run workflows on your own hardware. 

To do that, you have to run the following command on your server:

```bash
curl -fsSL https://get.dstack.ai/runner -o get-dstack-runner.sh
sudo sh get-dstack-runner.sh
dstack-runner config --token <token>
dstack-runner start
```

Your `token` value can be found in `Settings`:

![](images/dstack_quickstart_token.png){ lazy=true width="1060" }

If you've done this step properly, you'll see your server on the `Runners` page:

![](images/dstack_quickstart_runners.png){ lazy=true width="1060" }

## Step 2: Install the CLI

Now, to be able to run workflows, install and configure the dstack CLI:

```bash
pip install dstack -U
dstack config --token <token> 
```

## Step 3: Clone the repo

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

## Step 4: Run workflows

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

## Step 5: Tag runs

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
Instead, it will reuse the artifacts of the tagged workflow.

!!! info ""
    Keep in mind that you can tag as many runs as you want. When you refer to a workflow via a tag, 
    dstack will use the job that has the corresponding tag, workflow name, and variables.

It's now time to give a try to dstack, and run your first workflow.
