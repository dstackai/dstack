# Quickstart

This quickstart guide will introduce you to the key concepts and help you with the first steps of using dstack.

## Install the CLI

To run workflows, we'll need the dstack CLI. Here's how to install and configure it:

```bash
pip install dstack -U
dstack config --token <token> 
```

Your token value can be found in `Settings`.

[//]: # (![]&#40;images/dstack_quickstart_token.png&#41;{ lazy=true width="1060" })

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

The `download` workflow downloads the [MNIST](http://yann.lecun.com/exdb/mnist/) dataset
to the `data` folder and saves it as an artifact.

Once you run this workflow, you'll be able to assign a tag to that run, and reuse its output artifacts
in other workflows, e.g. the `train` workflow.

## Add your cloud credentials

To let dstack provision the infrastructure required for your workflows in your cloud account, you have to add
your cloud credentials in `Settings` | `Clouds`.

![](images/dstack_on_demand_settings.png){ lazy=true width="1080" }

[//]: # (Ellaborate on credentials)

## Run the download workflow

Let's go ahead and run the `download` workflow via the CLI:

```bash
dstack run download
```

!!! warning "Repository directory"
    Make sure you run the CLI from the repository directory    

Use the `Runs` page in the user interface to watch the progress of your workflow.

If you see your run failed, make sure to check the logs to find out the reason. Once the problem 
is fixed, feel free to re-run the workflow.

## Assign a tag

In order to use the output artifacts of our run in other workflows, we need to assign a tag to our finished run.
You can do it via the user interface.

In our example, the`train` workflow refers to the `latest` tag in its `depends-on` clause. To make it work,
we need to assign this tag to our finished `download` workflow. Tags can be assigned to finished runs via
the user interface.

## Run the train workflow

Once the required tag is created, let's go ahead and run the `train` workflow:

```bash
dstack run train
```

[//]: # (TODO: Tell how to pass arguments)

[//]: # (Mention how to change resources and everything else)

[//]: # (Mention local changes, ideally with a screenshot)

## Download artifacts

As a workflow is running, its output artifacts are saved in real-time.
You can browse them via the user interface or the CLI.

To download the artifacts locally, use the CLI:

```bash
dstack artifacts download <run-name>
```

[//]: # (TODO: Add screenshots)

[//]: # (TODO: Mention artifacts upload)