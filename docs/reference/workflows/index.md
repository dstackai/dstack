# Workflows

Workflows can be defined in the `.dstack/workflows.yaml` file within your 
project directory.

For every workflow, you can specify the provider, dependencies, commands, what output 
folders to store as artifacts, and what resources the instance would need (e.g. whether it should be a 
spot/preemptive instance, how much memory, GPU, etc.) 

## Basic example

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: "train"
        provider: bash
        deps:
          - tag: some_tag
        python: 3.10
        commands:
          - pip install requirements.txt
          - python src/train.py
        artifacts: 
          - path: checkpoint
        resources:
          interruptible: true
          gpu: 1
    ```

## Workflow syntax

Let's walk through the syntax of the `.dstack/workflows.yaml` file.

The root property of the file is always `workflows`. It contains a list of project workflows.

For every workflow, the following properties are required:

- `name` - (Required) The name of the workflow. Use this name with `dstack run` to run the corresponding workflow.
- `provider` - (Required) The name of the workflow provider. It defines how the workflow is executed and what other properties 
  can be specified for the workflow.

The following properties are optional:

- `deps` - (Optional) A list of the workflow's dependencies. The output artifacts of these dependencies
  are mounted as local folders before the workflow starts to run.
- `help` - (Optional) A description with what the workflow does (for documentation purposes).

!!! info "NOTE:"
    Other workflow properties depend on the selected `provider`. Check out the [Providers](../providers/index.md) page 
    to see what providers are supported and how to use them.

## Deps

The `deps` property defienes the workflow's dependencies. The output artifacts of these dependencies are 
mounted as local folders before the workflow starts to run.

There are two ways to define dependencies: via tags and via workflows.

#### Tags

The first way to specify a dependency is to use the `tag` property with a name of a tag:

```yaml
deps:
  - tag: some_tag
```

Here, `some_tag` is a name of a tag.

If you'd like to refer to a tag from another project, you have to prepend the tag with the short name of 
the project repository.

Here's an example:

```yaml
deps:
  - tag: dstackai/dstack/some_tag
```

#### Workflows

The second way to specify a dependency is to use the `workflow` property with a name of a workflow:

```yaml
deps:
  - workflow: some_workflow
```

Similar to tags, you can refer to workflows from other projects:

```yaml
deps:
  - workflow: dstackai/dstack/some_workflow
```

In that case, dstack will use the output artifacts of the most last run of the specified workflow.

## Secrets

Secrets allow to use sensitive data within workflows (such as passwords or security tokens) without 
hard-coding them inside the code.

A secret has a name and a value. All secrets are passed to the running workflows via environment variables.

Secrets can be managed via the `dstack secrets` CLI command.