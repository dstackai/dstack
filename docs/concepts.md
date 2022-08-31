## Workflows

Workflows are defined declaratively in the `.dstack/workflows.yaml` file within the
project. Every workflow may specify the provider, dependencies, commands, artifacts,
infrastructure resources, environment variables, and more.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: "train"
        provider: bash
        deps:
          - tag: some_tag
        python: 3.10
        env:
          - PYTHONPATH=mnist
        commands:
          - pip install requirements.txt
          - python src/train.py
        artifacts:
          - path: checkpoint
        resources:
          interruptible: true
          gpu: 1
    ```

Providers define how the workflow is executed and what properties can be specified for the workflow.

### Run command

When you run the workflow via the `dstack run` CLI command, dstack create the cloud instance(s) within a minute,
and runs the workflow. You can see the output of your workflow in real-time.

```shell
$ dstack run train

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

...
```

!!! info "NOTE:"
    As long as your project is under Git, you don't have to commit local changes before using the `dstack run` CLI command.
    dstack tracks local changes automatically.

## Artifacts

Every workflow may have its output artifacts. By default, dstack saves them in real-time as the workflow is running.

Artifacts can be accessed via the `dstack artifacts` CLI command.

## Tags

Tags help manage data.

For example, you can assign a tag to a finished workflow to use its output artifacts from other workflows.

Also, you can create a tag by uploading data from your local machine.

To make a workflow use the data via a tag, one has to use the `deps` property in `.dstack/workflows.yaml`.

Example:

```yaml
deps:
  - tag: some_tag
```

You can refer to tags from other projects as well.

Tags can be managed via the `dstack tags` CLI command.

## Backend

The dstack CLI uses your local credentials (e.g. the default AWS environment variables
or the credentials from `~/.aws/credentials`.) to provision infrastructure and store data.

All the state and artifacts are stored in an S3 bucket that can be configured via
the `dstack config` CLI command.

Multiple users may work with multiple projects within the same S3 bucket (e.g. for collaboration and
reuse of tags across projects).