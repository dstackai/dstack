# Quickstart

This quickstart guide will introduce you to the key concepts and help you with the first steps of using dstack.

## Install the CLI

To run workflows and providers, we'll need the dstack CLI. Here's how to install and configure it:

```bash
pip install dstack -U
dstack config --token <token> 
```

Your token value can be found in `Settings`:

![](images/dstack_quickstart_token.png){ lazy=true width="1060" }

## Clone the repo

In this quickstart guide, we'll use the 
[`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples) GitHub repo. Go ahead and clone this 
repo. Feel free to use the Terminal or open the repo wth your favourite IDE.

```bash
git clone https://github.com/dstackai/dstack-examples.git
cd dstack-examples
```

If you open the `.dstack/workflows.yaml` file, you'll see the following content:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: download
        help: "Downloads the MNIST dataset"
        provider: python
        file: "download.py"
        requirements: "requirements.txt"
        artifacts: ["data"]

      - name: train
        help: "Trains a model and saves the checkpoints"
        depends-on:
          - download:latest
        provider: python
        file: "train.py"
        requirements: "requirements.txt"
        artifacts: ["model"]
        resources:
          gpu: 1
    ```

[//]: # (Migrate to PyTorch Lightning)

[//]: # (TODO: Add a Streamlit app example)

The first workflow is `download`. It downloads the [MNIST](http://yann.lecun.com/exdb/mnist/) dataset
to the folder `data` and saves it as an artifact.

Once you run this workflow, you'll be able to assign a tag to that run, and reuse its output artifacts
in other workflows, e.g. the `train` workflow.

## Link your cloud account

To let dstack provision the infrastructure required for your workflows in your AWS account, you have to provide
dstack the corresponding credentials. To do that, go to the `Settings`, and then `AWS`.

Here, provide `AWS Access Key ID` and `AWS Secret Access Key` that have the
[corresponding](runners.md#on-demand-runners) permissions to create EC2 instances in your AWS account.

![](images/dstack_on_demand_settings.png){ lazy=true width="1080" }

## Run the download workflow

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

## Assign a tag

In order to use the output artifacts of our run in other workflows, we need to assign a tag to our finished run, e.g.
via the user interface.

Because our `train` workflow refers to the `latest` tag in its `depends-on` clause, go ahead and assign the `latest`
tag to our finished `download` workflow.

[//]: # (TODO: Consider auto-tagging with latest)

## Run the train workflow

Now that the finished `download` workflow is tagged with `latest`, everything is ready to run the `train` workflow.

Let's go ahead and run the `train` workflow:

```bash
dstack run train
```

[//]: # (TODO: Tell how to pass arguments)

When we run a workflow, dstack automatically provisions the required infrastructure.
You can edit the `resources` parameter to change the hardware requirements of the workflow:

```yaml
resources:
  memory: 64GB
  gpu: 4
```

## Download artifacts

As a workflow is running, its output artifacts are saved in real-time.
You can browse its output artifacts via the user interface or the CLI.

To download the artifacts locally, use the following CLI command:

```bash
dstack artifacts download <run-name>
```

[//]: # (TODO: Add screenshots)

[//]: # (TODO: Mention artifacts upload)