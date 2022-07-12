# Workflows

## About workflows

[//]: # (TODO: Mention that you can define workflows and run them by their name or run them directly from the CLI)

Workflows allow to run any machine learning tasks in your cloud account via the CLI. 
These tasks can include preparing data, training models, and running applications. 
When you run a workflow, dstack automatically provisions the required infrastructure, dependencies, and tracks 
output artifacts.

You can define workflows in the `.dstack/workflows.yaml` file within your project 
directory and run them by a name via the CLI.

[//]: # (You don't have to worry about )
[//]: # (tracking code, data, or infrastructure as dstack handles everything automatically.)

## Workflow syntax

Let's walk through the syntax of this file. Here's a basic example:

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

[//]: # (!!! tip "Source code")
[//]: # (    You can find the full source code of the example in the [dstackai/dstack-examples]&#40;https://github.com/dstackai/dstack-examples&#41; GitHub repo.)

## Providers

The `provider` argument defines how the workflow is executed. Every provider may have its own arguments.

For example, with the [`python`](providers/python.md) provider, we can pass `file` (the file to run),
`requirements` (the file with requirements), `artifacts` (what folders) to save as output artifacts,
and `resources` (what hardware resources are required to run the workflow, e.g. GPU, memory, etc).

[//]: # (TODO: Provide mode provider examples)

dstack offers a variety of [built-in providers](/providers) that allow you to run any machine learning task, deploy an application, 
or launch a dev environment.

[//]: # (TODO: Tell how to use custom providers)

[//]: # (TODO: Add a link to the Providers Reference)

## Dependencies

[//]: # (TODO: Mention how to upload artifacts from the CLI)

In the example above, you can notice that the `train` workflow has a `depends-on` argument.
This argument defines dependencies to other workflows.

For example, if you want dstack to run the `download` workflow before the `train` workflow,
you can use the following syntax:

```yaml
depends-on:
  - download 
```

If you run the `train` workflow, dstack will run both the `download` and the `train` workflows. 
The output artifacts of the `download` workflow will be passed to the 
`train` workflow.

[//]: # (If you want dstack to reuse the latest run of the `download` workflow, you can use the following syntax:)

[//]: # (```yaml)
[//]: # (depends-on:)
[//]: # (  - download )
[//]: # (```)

[//]: # (In case you want to use the output artifacts of a particular run of the `download` workflow, you can use its tag:)

[//]: # (```yaml)
[//]: # (depends-on:)
[//]: # (  - @<tag-name>)
[//]: # (```)

In case you want to run the `download` workflow each time you run the `train` workflow,
and instead would like to reuse the output artifacts of a particular run of the `download` workflow, 
you can refer to that run via a tag:

```yaml
depends-on:
  - download:<tag-name>
```

Tags can be assigned to finished runs via the CLI or the user interface. Tags allow to version output artifacts
for later reuse.

[//]: # (TODO: Tell about dstack artifacts upload)

[//]: # (## Variables)

[//]: # ()
[//]: # (You can parametrize workflow by defining variables in the `.dstack/variables.yaml` file.)

[//]: # (Here's an example:)

[//]: # ()
[//]: # (=== ".dstack/variables.yaml")

[//]: # (    ```yaml)

[//]: # (    variables:)

[//]: # (     train:)

[//]: # (       batch-size: 64)

[//]: # (       test-batch-size: 1000)

[//]: # (       epochs: 1)

[//]: # (       lr: 1.0)

[//]: # (       gamma: 0.7)

[//]: # (       seed: 1)

[//]: # (       log-interval: 10)

[//]: # (    ```)

[//]: # ()
[//]: # (When run workflows, dstack passes variables to the workflow as environment variables.)

[//]: # ()
[//]: # (For example, if you are running a Python script, you can access them the following way:)

[//]: # ()
[//]: # (```python)

[//]: # (import os)

[//]: # ()
[//]: # (batch_size = os.environ.get&#40;"BATCH_SIZE"&#41;)

[//]: # (```)

[//]: # ()
[//]: # (!!! info "")

[//]: # (    If you want, you can also use variables within the `.dstack/workflows.yaml` file, via the following syntax: `${{ variable_name }}`.)

[//]: # ()
[//]: # (Any variable can be overridden via the CLI when you run a workflow.)

## Run workflows

You can run any of the workflows defined in `.dstack/workflows.yaml` using the CLI:

```bash
dstack run download 
```

!!! warning "Be sure to run the CLI from the repository directory"

    As long as your project is under Git, you don't have to commit local changes before running workflows.
    dstack tracks staged local changes automatically and allows you to see them in the user interface
    for every run.

Once you've run a workflow, you'll see it in the user interface.
To see recent runs from the CLI, use the following command:

```bash
dstack runs
```

[//]: # (TODO: Show a screennshot of repo diff)

[//]: # (TODO: Mention how to pass provider args to the script)

[//]: # (### Variables)

[//]: # ()
[//]: # (If you defined workflow variables within the `.dstack/variables.yaml` file, you can override any of them via the )

[//]: # (arguments of the `dstack run` command: )

[//]: # ()
[//]: # (```bash)

[//]: # (dstack run train --epoch 100 --seed 2)

[//]: # (```)

!!! tip "You can run workflows without defining them in `.dstack/workflows.yaml`"

    If you want, you can run a workflow solely via the CLI by using the name of the provider: 

    ```bash
    dstack run python train.py \
      --dep download:latest --artifact checkpoint --gpu 1 \ 
      --epoch 100 --seed 2 --batch-size 128
    ```

### Workflow logs

The output of running workflows is tracked in real-time and can be accessed through the user interface
or the CLI.

To access the output through the CLI, use the following command:

```bash
dstack logs <run-name>
```

If you'd like to see the output in real-time through the CLI, add the `-f` (or `--follow`) argument:

```bash
dstack logs <run-name> -f
```

!!! warning "Don't print experiment metrics to the logs"
    Instead, it's recommended that you use specialized tools such as WandB, Comet, Neptune, etc.

[//]: # (TODO: Add a link to more information on experiment tracking)

## Workflow artifacts

By default, the output artifacts are tracked in real-time and can be accessed either via the user interface
or the CLI.

To browse artifacts through the CLI, use the following command:

```bash
dstack artifacts list <run-name>
```

To download artifacts locally, use the following command:

```bash
dstack artifacts download <run-name>
```

[//]: # (TODO: Add screenshots)

[//]: # (TODO: Tell about stopping and restarting workflows)

[//]: # (TODO: Add a link to the CLI reference)

[//]: # (TODO: Add a link to Providers Reference)

## Secret variables

If you plan to use third-party services from your workflows, you can use dstack's secrets 
to securely pass passwords and tokens.

Adding secrets can be done via `Settings`.

The configured secrets are passed to the workflows as environment variables. 

Here's an example of how you can access them from Python: 

```python
import os

wandb_api_key = os.environ.get("WANDB_API_KEY")
```