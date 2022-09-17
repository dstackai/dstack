# run

The `run` command runs a workflow within the current Git repository. 

Once you run the workflow, dstack creates the required cloud instance(s) within a minute,
and runs your workflow. If you run it in the attached mode, you'll see the output in real-time as your 
workflow is running.

You can either pass a name of one of the workflows defined in 
the `./dstack/workflows.yaml` file, or pass all the parameters right in the command line.

!!! info "NOTE:"
    Make sure to use the CLI from within a Git repository directory.
    When you run a workflow, dstack detects the current branch, commit hash, and local changes.

### Usage

```shell
dstack run [-d] [-h] (WORKFLOW | PROVIDER) [ARGS ...]
```

#### Arguments reference

One of the following arguments is required:

- `WORKFLOW` - A name of one of the workflows defined in 
   the `./dstack/workflows.yaml` file.
- `PROVIDER` – A name of the provider, in case you want to
   run a workflow that is not defined in the `./dstack/workflows.yaml` file. 

The following arguments are optional:

-  `-d`, `--detach` - (Optional) Run the workflow in the detached mode. Means, the `run` command doesn't
  poll for logs and workflow status, but exits immediately. 
- `ARGS` – (Optional) Use these arguments to override any of the workflow or provider parameters

To see the help output for a particular workflow or provider, use the following command:

```shell
dstack run (WORKFLOW | PROVIDER) --help
```

!!! info "NOTE: " 
    If you run a workflow by name, you can override any of the workflow parameters defined 
    in the `./dstack/workflows.yaml` file.
 
    Example:
 
    ```bash
    dstack run train -i --gpu 1
    ```

### Examples

Here's how to run the `train` workflow defined in the `.dstack/workflows.yaml` file:

```shell
$ dstack run train

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

...
```

If you want, you can run a workflow without defining it in `.dstack/workfows.yaml`:

```shell
$ dstack run bash -c "pip install requirements.txt && python src/train.py" \
  -d :some_tag -a checkpoint -i --gpu 1

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

...
```