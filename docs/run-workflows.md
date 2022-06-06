# Run workflows

This guide will show you how to run and manage workflows.

## Prerequisites

Before you'll follow this guide, ensure the following:

* You've set up your dstack account according to the [Setup](setup.md) guide 
* You've defined workflows according to the [Define workflows](define-workflows.md) guide
* Make sure your project is under Git. 
  If your Git repository is private, make sure that dstack is [granted](setup.md#step-3-configure-git-credentials) access to it.

## Run command

You can run any of the defined workflows using the CLI.

!!! info ""
    Be sure to invoke the dstack CLI from the project directory.

```bash
dstack run download 
```

Once you've run a workflow, you'll see it in the user interface.

**Git local changes**

As long as your project is under Git, you don't have to commit local changes before running workflows.
dstack tracks the staged local changes automatically and allows you to see them in the user interface
for every run.

[//]: # (TODO: Show a screennshot of repo diff)

**Workflow variables**

If you defined workflow variables within the `.dstack/variables.yaml` file, you can override any of them via the 
arguments of the `dstack run` command: 

```bash
dstack run train --gpu 2 --epoch 100 --seed 2
```

**List recent runs**

To see recent runs from the CLI, use the following command:

```bash
dstack runs
```

[//]: # (TODO: Tell about statuses)

[//]: # (TODO: Tell about availability issues)

## Browse logs

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

!!! info "Experiment metrics"
    Be sure not to use logs to track experiment metrics. Instead, it's recommended
    that you use specialized APIs such as TensorBoard, WandB, Comet, or Neptune.

[//]: # (TODO: Add a link to more information on experiment tracking)

## Browse artifacts

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