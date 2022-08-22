## Define workflows

Workflows can be defined in the `.dstack/workflows.yaml` file within your 
project.

For every workflow, you can specify the provider, dependencies, commands, what output folders to store
as artifacts, and what resources the instance would need (e.g. whether it should be a 
spot/preemptive instance, how much memory, GPU, etc).

```yaml
workflows:
  - name: "train"
    provider: bash
    deps:
      - :some_tag
    python: 3.10
    commands:
      - pip install requirements.txt
      - python src/train.py
    artifacts: [ "checkpoint" ]
    resources:
      interruptible: true
      gpu: 1
```

Find more details and examples on how to define workflows [here](workflows/index.md).

## Run workflows

Once you run the workflow, dstack will create the required cloud instance within a minute,
and will run your workflow. You'll see the output in real-time as your 
workflow is running.

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

!!! info "NOTE:"
    Make sure to always run the CLI from the project repository directory.
    As long as your project is under Git, you don't have to commit local changes before using the run command.

## Manage tags

Tags help managing data. You can assign tags to finished workflows to reuse their output artifacts 
in other workflows. Another way to use tags is to upload data to dstack from your local machine
and assign n tag to it to use this data in workflows.

Here's how to assign a tag to a finished workflow:

```shell
dstack tags add TAG --run-name RUN
```

Here, `TAG` is the name of the tag and `RUN` is the name of the finished workflow run.

If you want to data from your local machine and save it as a tag to use it from other workflows,
here's how to do it:

```shell
dstack tags add TAG --local-dir LOCAL_DIR
```

Once a tag is created, you can refer to it from workflows, e.g. from `.dstack/workflows.yaml`:

```yaml
deps:
  - :some_tag
```

## Manage artifacts

The artifacts command allows you to browse or download the contents of artifacts.

Here's how to browse artifacts:

```shell
dstack artifacts list (RUN | :TAG)
```

Here's how to download artifacts:

```shell
dstack artifacts download (RUN | :TAG) [OUTPUT_DIR]
```
