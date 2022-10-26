# dstack run

This command runs a workflow defined in the current Git repo. 

The command provisions the required compute resources (in a configured cloud), fetches the same version of code 
(as you have locally), downloads the deps, and runs the workflow, saves artifacts, and tears down compute resources.

[//]: # (!!! info "NOTE:")
[//]: # (    Make sure to use the CLI from within a Git repo directory.)
[//]: # (    When you run a workflow, dstack detects the current branch, commit hash, and local changes.)

### Usage

```shell
dstack run [-h] WORKFLOW [-d] [-l] [-t TAG] [ARGS ...]
```

#### Arguments reference

The following arguments are required:

- `WORKFLOW` - (Required) A name of one of the workflows defined in 
   the `./dstack/workflows.yaml` file.

The following arguments are optional:

- `-t TAG`, `--tag TAG` - (Optional) A tag name. Warning, if the tag exists, it will be overridden.
- `-l`, `--local`, - (Optional) Run the workflow locally. Requires Docker
  or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) to be installed locally.
-  `-d`, `--detach` - (Optional) Run the workflow in the detached mode. Means, the `run` command doesn't
  poll for logs and workflow status, but exits immediately. 
- `ARGS` – (Optional) Use these arguments to override workflow parameters defined in `.dstack/workflows.yaml`
-  `-h`, `--help` - (Optional) Shows help for the `dstack run` command. Combine it with the name of the workflow
   to see how to override workflow parameters defined in `.dstack/workflows.yaml`

Use `ARGS` to override any of the workflow parameters defined in the `./dstack/workflows.yaml` file.

!!! info "NOTE:"
    By default, it runs it in the attached mode, so you'll see the output in real-time as your 
    workflow is running.
