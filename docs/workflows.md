# Workflows

Workflows allow you to define your common tasks and run them locally or in the cloud
while dstack takes care of tracking code, dependencies, logs, output artifacts,
and provisioning required infrastructure.

Workflows are defined in the `.dstack/workflows.yaml` file within your project directory. 
Once workflows are defined, you can run any of them interactively through dstack CLI. 

[//]: # (You don't have to worry about )
[//]: # (tracking code, data, or infrastructure as dstack handles everything automatically.)

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

## Dependencies

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

Tags allow you to version the outputs of workflows and reuse their output artifacts in other workflows.

[//]: # (TODO: Tell about dstack artifacts upload)

## Providers

Each workflow must include a `provider` parameter. This parameter tells which program runs the workflow.
Every provider may have its own list of required and non-required parameters.

[//]: # (TODO: Provide mode provider examples)

To see the entire list of built-in providers, they parameters, and examples, check out the [providers](https://github.com/dstackai/dstack/tree/master/providers#readme) page.

[//]: # (TODO: Tell how to use custom providers)

[//]: # (TODO: Add a link to the Providers Reference)

## Variables

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