# Run workflows

This guide will show you how to run and manage workflows.

## Prerequisites

Before you'll follow this guide, ensure the following:

* You've set up your dstack account according to the [Setup](setup.md) guide 
* You've defined workflows according to the [Define workflows](define-workflows.md) guide

!!! info "Git"
    Finally, make sure your project is under Git and dstack is [granted](setup.md#step-3-configure-git-credentials) access to it.

    As to your local Git changes, don't worry, you don't have to commit then before running workflows.
    dstack tracks local changes automatically.

## Run workflows

You can run any of the defined workflows using the CLI.

!!! info ""
    Be sure to run the CLI from the project directory.

```bash
dstack run train-mnist 
```

If you want to override any of the variables (from `.dstack/variables.yaml`) when you run a workflow, 
you can do it via the arguments to the `dstack run` command. 
Here's an example:

```bash
dstack run train --gpu 2 --epoch 100 --seed 2
```

Once you run a workflow, you'll see it in the user interface.

[//]: # (TODO: Tell about logs and artifacts)

[//]: # (TODO: Add screenshots)

[//]: # (TODO: Tell about statuses)

[//]: # (TODO: Tell about availability issues)

[//]: # (TODO: Tell about local diffs in the user interface)

[//]: # (TODO: Tell about stopping and restarting workflows)

[//]: # (TODO: Add a link to the CLI reference)