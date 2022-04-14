# dstack: Automate Data and Training Workflows Easily 

An open-core platform to automate data and training workflows, provision infrastructure, and version data and models.

## High Level Features

* dstack allows you to define workflows and infrastructure requirements as code using declarative Configuration files.
 When you run a workflow, dstack provisions the required infrastructure on-demand.
* Either use your existing hardware or provision infrastructure on-demand in your own cloud account (e.g. AWS, GCP,
  Azure, etc.).
* Version data and models produced by workflows automatically. Assign tags to successful runs to refer to their
  artifacts from other workflows.
* When defining a workflow, you can either use the built-in providers (that support specific use-cases), or create
  custom providers for specific use-cases using dstack's Python API.

## Getting Started

### Step 1: Set up runners

`Runners` are machines that run submitted `Workflows`. dstack supports two types of `Runners`: the `on-demand` `Runners`
and `self-hosted` `Runners`. 

The `on-demand` `Runners` are created automatically by dstack (in the computing vendor, configured by the user, e.g. `AWS`) 
for the time of running `Workflows`. The `self-hosted` `Runners` can be set up manually to run `Workflows`
using the user's own hardware.

### Option 1: Set up on-demand runners

To use the `on-demand` `Runners`, go to the `Settings`, then `AWS`.

Here, you have to provide `AWS Access Key ID` and `AWS Secret Access Key` that have the
corresponding permissions to create EC2 instances in your `AWS` account.

Once you've provided `Credentials`, use the `Add limit` button to configure limits:

<img src="docs/images/dstack_on_demand_settings.png" width="1060" />

The configured `Limits` represent the maximum number of EC2 instances of the specific `Instance Type` and in the specific `Region`, that
dstack can create at one time to run `Workflows`.

### Option 2: Set up self-hosted runners

As an alternative to `on-demand` `Runners`, you can run `Workflows` on your own hardware. 

To do that, you have to run the following command on your server:

```bash
curl -fsSL https://get.dstack.ai/runner -o get-dstack-runner.sh
sudo sh get-dstack-runner.sh
dstack-runner config --token <token>
dstack-runner start
```

Your `token` value can be found in `Settings`:

<img src="docs/images/dstack_quickstart_token.png" width="1060" />

If you've done this step properly, you'll see your server on the `Runners` page:

<img src="docs/images/dstack_quickstart_runners.png" width="1060" />

## Step 2: Install the CLI

Now, to be able to run `Workflows`, install and configure the dstack `CLI`:

```bash
pip install dstack -U
dstack config --token <token> 
```

## Step 3: Clone the repo

Just to get started, we'll run `Workflows` defined in 
[`github.com/dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples).

```bash
git clone https://github.com/dstackai/dstack-examples.git
cd dstack-examples
```

The project includes two `Workflows`: `download-mnist` and `train-mnist`. The frst `Workflow` downloads the [MNIST](http://yann.lecun.com/exdb/mnist/) dataset,
whilst the second `Workflow` trains a model using the output of the first `Workflow` as an input:

`.dstack/workflows.yaml`:

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

`.dstack/variables.yaml`:

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

Go ahead, and run the `train-mnist` `Workflow` using the following command:

```bash
dstack run train-mnist 
```

If you want to change any of the `Variables`, you can do that in `.dstack/variables.yaml`, or from the `CLI`:

```bash
dstack run train-mnist --gpu 2 --epoch 100 --seed 2
```

When you run `train-mnist`, because `train-mnist` depends on `download-mnist`, dstack will create a run with two `Jobs`: 
one for `train-mnist` and one for `download-mnist`:

<img src="docs/images/dstack_quickstart_runs.png" width="1060" />

## Step 5: Tag runs

When the `Run` is finished, you can assign a `Tag` to it, e.g. `latest`:

```bash
dstack tag cowardly-goose-1 latest
```

Now, you can refer to this tagged `Workflow` from `.dstack/workflows.yaml`:

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

Now, if you run the `train-mnist` `Workflow`, dstack won't create a `Job` for the `download-mnist` `Workflow`.
Instead, it will reuse the `Artifacts` of the tagged `Workflow`.

## Repository

This repository contains dstack's open-source and public code, documentation, and other key resources:

* [`providers`](providers): The source code of the built-in dstack workflow providers
* [`cli`](cli): The source code of the dstack CLI pip package
* [`docs`](docs): A user guide to the whole dstack platform ([docs.dstack.ai](https://docs.dstack.ai))

Here's the list of other packages that are expected to be included into this repository with their source code soon:

* `runner`: The source code of the program that runs dstack workflows
* `server`: The source code of the program that orchestrates dstack runs and jobs and provides a user interface
* `examples`: The source code of the examples of using dstack

## Contributing

Please check [CONTRIBUTING.md](CONTRIBUTING.md) if you'd like to get involved in the development of dstack.

## License

Please see [LICENSE.md](LICENSE.md) for more information about the terms under which the various parts of this repository are made available.

## Contact

Find us on Twitter at [@dstackai](https://twitter.com/dstackai), join our [Slack workspace](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ) for quick help and support.

Project permalink: `https://github.com/dstackai/dstack`