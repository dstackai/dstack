## Workflows

Workflows are defined declaratively in the `.dstack/workflows.yaml` file within the
project. Every workflow may specify the provider, dependencies, commands, artifacts,
hardware requirements, environment variables, and more.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: "train"
        provider: bash
        deps:
          - tag: mnist_data
        python: 3.10
        commands:
          - pip install requirements.txt
          - python mnist/train.py
        artifacts:
          - path: checkpoint
        resources:
          interruptible: true
          gpu: 1
    ```

When you run the workflow via the `dstack run` CLI command, dstack creates the cloud instance(s) within a minute,
and runs the workflow. You can see the output of your workflow in real-time.

```shell
$ dstack run train

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

...
```

## Providers

The provider defines how the workflow is executed and what properties can be 
specified for the workflow.

Providers allow to run tasks, applications, and even dev environments, such as 
IDEs and Jupyter notebooks.

## Environment
    
dstack automatically sets up environment for the workflow. It pre-installs the right CUDA driver, 
the right version of Python, and Conda.

## Git

You can run the dstack CLI only from inside a Git repo directory.

When you run a workflow, dstack detects the current branch, commit hash, 
and local changes, and uses it on the cloud instance(s) to run the workflow.

## Artifacts and tags

Every workflow may have output artifacts. They can be accessed via the `dstack artifacts` CLI command.

You can assign tags to finished workflows to reuse their output artifacts from other workflows.

You can also use tags to upload local data and reuse it from other workflows.

If you've added a tag, you can refer to it as to a dependency via the `deps` property of your workflow 
in `.dstack/workflows.yaml`:

```yaml
deps:
  - tag: mnist_data
```

You can refer not only to tags within your current Git repo but to the tags from your other 
repositories.

Here's an example how the workflow refers to a tag from the `dstackai/dstack-examples` repo:

```yaml
deps:
  - tag: dstackai/dstack-examples/mnist_data
```

Tags can be managed via the `dstack tags` CLI command.

## Backend

The dstack CLI uses your local credentials (e.g. the default AWS environment variables
or the credentials from `~/.aws/credentials`.) to provision infrastructure and store data.

All the state and artifacts are stored in an S3 bucket that can be configured via
the `dstack config` CLI command.

Multiple users may work with multiple projects within the same S3 bucket (e.g. for collaboration and
reuse of tags across projects).