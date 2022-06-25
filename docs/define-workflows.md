# Define workflows

This guide gives a high-level overview of what workflows are, and how they are defined.

## About workflows

Training models may involve multiple sequential workflows, such as preparing data,
training, deployment, etc. Every workflow may produce output data, depend on the outputs
of other workflows, and have its own infrastructure requirements.

dstack allows you to define these workflows via declarative configuration files. This can include what these workflows do, 
how they depend on each other, what outputs they produce, and what infrastructure they require to run.

Workflows are defined in the `.dstack/workflows.yaml` file within your project directory. 
Once workflows are defined, you can run any of them interactively through dstack CLI. 

You don't have to worry about 
tracking code, data, or infrastructure as dstack handles everything automatically.

### Example

Here's a basic example of how workflows can be defined:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: download
        help: "Downloads the training data" 
        provider: python
        file: "download.py"
        artifacts: ["data"]
    
      - name: train
        help: "Trains a model and saves the checkpoints"
        depends-on:
          - download:latest
        provider: python
        file: "train.py"
        artifacts: ["model"]
        resources:
          gpu: 1
    ```

!!! tip "Source code"
    You can find the full source code of the example in the [dstackai/dstack-examples](https://github.com/dstackai/dstack-examples) GitHub repo.

Let's now walk through the syntax of this file to understand how it works.

## Workflow dependencies

When you want to pass the outputs from one workflow to another one, you have to use the `depends-on` property.

There are two ways to do specify this property:

### Runtime dependencies

A dependency is called a runtime dependency if it includes only a name of a workflow (without a tag):

```yaml
depends-on:
  - download 
```

In this case, if you run the `train` workflow, dstack will run both `download` and `train` workflows in a sequence.
The outputs of the `download` workflow will be passed to the `train` workflow.

### Tag dependency

A dependency is called a tag dependency if you add a tag name to the name of a workflow.

Here's an example:

```yaml
depends-on:
  - download:latest 
```

In this case, you first have to run the `download` workflow, and when it's finished, assign a tag to it, e.g. `latest` 
or anything else. After that, you can run the `train` workflow using the syntax from above.
The `train` workflow will then use the output artifacts from the tagged `download` that we ran earlier.

!!! tip ""
    Tags allow you to version the outputs of workflows and reuse their output artifacts in other workflows.

[//]: # (TODO: Tell about dstack artifacts upload)

## Provider-specific properties

Each workflow must include a `provider` property. This property tells which program will run the workflow.

### Python

The most common provider is `python`. It supports the following properties:


| Parameter      | Required         | Description                                                                  |
|----------------|------------------|------------------------------------------------------------------------------|
| `file`         | :material-check: | The path to the Python script                                                |
| `args`         |                  | The list of arguments for the Python script                                  |
| `requirements` |                  | The path to the `requirements.txt` file                                      |
| `version`      |                  | The major version of Python. The default value is `"3.10"`.                  |
| `environment`  |                  | Environment variables                                                        |
| `working_dir`  |                  | The working directory. The default value is the root directory.              |
| `artifacts`    |                  | The paths to the folders to save as output artifacts                         |
| `resources`    |                  | The hardware resources required to run the workflow (memory, CPU, GPU, etc.) |

[//]: # (TODO: Environment variables)

[//]: # (TODO: Artifacts)

[//]: # (TODO: Resources)

[//]: # (TODO: Add a link to the Providers Reference)

## Supported providers

Here's the list of all built-in providers:

| Name                                                                                   | Description                                               |
|----------------------------------------------------------------------------------------|-----------------------------------------------------------|
| [python](https://github.com/dstackai/dstack/tree/master/providers/python#readme)       | Runs a Python script                                      |
| [streamlit](https://github.com/dstackai/dstack/tree/master/providers/streamlit#readme) | Launches a Streamlit application                          |
| [lab](https://github.com/dstackai/dstack/tree/master/providers/lab#readme)             | Launches a JupyterLab application                         |
| [torchrun](https://github.com/dstackai/dstack/tree/master/providers/torchrun#readme)   | Runs a PyTorch training script on multiple nodes with GPU |
| [code](https://github.com/dstackai/dstack/tree/master/providers/code#readme)           | Launches a VS Code application                            |
| [notebook](https://github.com/dstackai/dstack/tree/master/providers/notebook#readme)   | Launches a Jupyter notebook application                   |
| [docker](https://github.com/dstackai/dstack/tree/master/providers/docker#readme)       | Runs a Docker image                                       |
| [curl](https://github.com/dstackai/dstack/tree/master/providers/curl#readme)           | Downloads the contents of a URL                           |

!!! info ""
    You can extend dstack by building [custom providers](custom-providers.md) using dstack's Python API.

[//]: # (TODO: Add a link to the Providers Reference)

## Workflow variables

You can parametrize workflow by defining variables in the `.dstack/variables.yaml` file.
Here's an example:

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

When run workflows, dstack passes variables to the workflow as environment variables.

For example, if you are running a Python script, you can access them the following way:

```python
import os

batch_size = os.environ.get("BATCH_SIZE")
```

!!! info ""
    If you want, you can also use variables within the `.dstack/workflows.yaml` file, via the following syntax: `${{ variable_name }}`.

Any variable can be overridden via the CLI when you run a workflow.

## Secrets

If you plan to use third-party services from your workflows, you can use dstack's secrets 
to securely pass passwords and tokens.

Adding secrets can be done via `Settings`.

The configured secrets are passed to the workflows as environment variables. 

Here's an example of how you can access them from Python: 

```python
import os

wandb_api_key = os.environ.get("WANDB_API_KEY")
```