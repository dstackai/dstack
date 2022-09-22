# dstack run

Use this command to run a workflow within the current Git repo. 

Once you run the workflow, dstack creates the required cloud instance(s) within a minute,
and runs your workflow. If you run it in the attached mode, you'll see the output in real-time as your 
workflow is running.

You can either pass a name of one of the workflows defined in 
the `./dstack/workflows.yaml` file, or pass all the parameters right in the command line.

!!! info "NOTE:"
    Make sure to use the CLI from within a Git repo directory.
    When you run a workflow, dstack detects the current branch, commit hash, and local changes.

### Usage

```shell
dstack run [-h] WORKFLOW [-d] [-t TAG] [ARGS ...]
```

#### Arguments reference

The following arguments are required:

- `WORKFLOW` - (Required) A name of one of the workflows defined in 
   the `./dstack/workflows.yaml` file.

The following arguments are optional:

- `-t TAG`, `--tag TAG` - (Optional) A tag name. Warning, if the tag exists, it will be overridden.
-  `-d`, `--detach` - (Optional) Run the workflow in the detached mode. Means, the `run` command doesn't
  poll for logs and workflow status, but exits immediately. 
- `ARGS` – (Optional) Use these arguments to override workflow parameters defined in `.dstack/workflows.yaml`
-  `-h`, `--help` - (Optional) Shows help for the `dstack run` command. Combine it with the name of the workflow
   to see how to override workflow parameters defined in `.dstack/workflows.yaml`

Use `ARGS` to override any of the workflow parameters defined in the `./dstack/workflows.yaml` file.

### Examples

Here's how to run the `train` workflow defined in the `.dstack/workflows.yaml` file:

```shell
$ dstack run train

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

...
```