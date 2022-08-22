# Workflows

Workflows can be defined in the `.dstack/workflows.yaml` file within your 
project.

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

## Workflows syntax

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

## Deps

The `deps` property defienes the workflow's dependencies. The output artifacts of these dependencies are 
mounted as local folders before the workflow starts to run.

There are two ways to define dependencies: via _Tags_ and via _Workflows_.

### Tags

The first way to specify a dependency is to use a _colon_ followed by a name of a tag:

```yaml
deps:
  - :some_tag
```

Here, `some_tag` is a name of a tag.

If you'd like to refer to a tag from another project, you have to prepend the tag with the short name of 
the project repository.

Here's an example:

```yaml
deps:
  - :dstackai/dstack/some_tag
```

### Workflows

The second way to specify a dependency is to use a workflow name:

```yaml
deps:
  - some_workflow
```

Similar to tags, you can refer to workflows from other projects:

```yaml
deps:
  - dstackai/dstack/some_workflow
```

In that case, dstack will use the output artifacts of the most last run of the specified workflow.

## Providers

Providers define how the workflow is executed and what properties can be specified for the workflow.
Providers may help run tasks, applications, dev environments and even distributed workflows.

### Main provider

<div class="grid cards" markdown>
- **Bash** 

    Runs shell commands

    [:octicons-arrow-right-24: Reference](../providers/bash.md)

</div>

### Other providers

<div class="grid cards" markdown>

- **VS Code** 

    Launches a VS Code dev environment

    [:octicons-arrow-right-24: Reference](code.md)

- **JupyterLab** 

    Launches a JupyterLab dev environment

    [:octicons-arrow-right-24: Reference](lab.md)

- **Jupyter Notebook** 

    Launches a Jupyter notebook

    [:octicons-arrow-right-24: Reference](notebook.md)

- **Torchrun** 

    Runs a distributed training

    [:octicons-arrow-right-24: Reference](torchrun.md)

- **Docker** 

    Runs a Docker image

    [:octicons-arrow-right-24: Reference](docker.md)

</div>