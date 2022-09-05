<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="300px"/>    

Git-based CLI to run ML workflows on cloud
______________________________________________________________________

[![PyPI](https://img.shields.io/pypi/v/dstack?style=for-the-badge&color=brightgreen)](https://pypi.org/project/dstack/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=for-the-badge&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
[![Slack](https://img.shields.io/badge/slack-chat-e01563?style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

[//]: # ([![twitter]&#40;https://img.shields.io/twitter/follow/dstackai.svg?style=social&label=Follow&#41;]&#40;https://twitter.com/dstackai&#41;)

</div>

## Intro

To run ML workflows, often your local machine is not enough. 
That’s why it's necessary to automate the process of running ML workflows within the cloud infrastructure.

Instead of managing infrastructure yourself, writing own scripts, or using cumbersome MLOps platforms, with dstack, 
you can focus on code while dstack does management of dependencies, infrastructure, and data for you.

dstack is an alternative to KubeFlow, SageMaker, Docker, SSH, custom scripts, and other tools used often to
run ML workflows.

### Primary features of dstack:

1. **Git-focused:** Define workflows and their hardware requirements as code.
   When you run a workflow, dstack detects the current branch, commit hash, and local changes.
2. **Data management:** Workflow artifacts are the 1st-class citizens.
   Assign tags to finished workflows to reuse their artifacts from other workflows. 
   Version data using tags.
3. **Environment setup:** No need to build custom Docker images or setup CUDA yourself. Just specify Conda 
   requirements and they will be pre-configured.
4. **Interruption-friendly:** Because artifacts can be stored in real-time, you can leverage interruptible 
   (spot/preemptive) instances. Workflows can be resumed from where they were interrupted.
5. **Dev environments:** Workflows may be not only tasks and applications but also dev environments, such as 
   IDEs and Jupyter notebooks.
6. **Very easy setup:** Install the dstack CLI and run workflows
   in the cloud using your local credentials. The state is stored in an S3 bucket. 
   No need to set up anything else.

## Installation

To use dstack, you'll only need the dstack CLI. No other software needs to be installed or deployed.

The CLI will use your local cloud credentials (e.g. the default AWS environment variables 
or the credentials from `~/.aws/credentials`.)

In order to install the CLI, you need to use pip:

```shell
pip install dstack
```

Before you can use dstack, you have to configure the dstack backend:

 * In which S3 bucket to store the state and the artifacts
 * In what region, create cloud instances.

To configure this, run the following command:

```shell
dstack config
Configure AWS backend:

AWS profile name (default):
S3 bucket name:
Region name:
```

The configuration will be stored in `~/.dstack/config.yaml`.

That's it. Now you can use dstack on your machine.

## Usage

### Define workflows

Workflows can be defined in the `.dstack/workflows.yaml` file within your 
project.

For every workflow, you can specify the provider, dependencies, commands, what output 
folders to store as artifacts, and what resources the instance would need (e.g. whether it should be a 
spot/preemptive instance, how much memory, GPU, etc.)

```yaml
workflows:
  - name: "train"
    provider: bash
    deps:
      - tag: mnist_data
    python: 3.10
    env:
      - PYTHONPATH=src
    commands:
      - pip install requirements.txt
      - python src/train.py
    artifacts: 
      - path: checkpoint
    resources:
      interruptible: true
      gpu: 1
```

### Run workflows

Once you run the workflow, dstack will create the required cloud instance(s) within a minute,
and will run your workflow. You'll see the output in real-time as your 
workflow is running.

```shell
$ dstack run train

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

...
```

**Environment setup:** dstack automatically sets up environment for the workflow. It pre-installs the right CUDA driver, 
the right version of Python, and Conda.

**Git:** When you run a workflow withing a Git repository, dstack detects the current branch, commit hash, 
and local changes, and uses it on the cloud instance(s) to run the workflow.

## Artifacts and tags

Every workflow may have its output artifacts. They can be accessed via the `dstack artifacts` CLI command.

You can assign tags to finished workflows to reuse their output artifacts from other workflows.

You can also use tags to upload local data and reuse it from other workflows.

If you've added a tag, you can refer to it as to a dependency via the `deps` property of your workflow 
in `.dstack/workflows.yaml`:

```yaml
deps:
  - tag: mnist_data
```

You can refer not only to tags within your current Git repository but to the tags from your other 
repositories.

Here's an example how the workflow refers to a tag from the `dstackai/dstack-examples` repository:

```yaml
deps:
  - tag: dstackai/dstack-examples/mnist_data
```

Tags can be managed via the `dstack tags` CLI command.

## Providers

dstack supports [multiple providers](https://docs.dstack.ai/providers) that allow running tasks, applications, 
and dev environments.

## Docs

More tutorials, examples, and the full CLI reference can be found at [docs.dstack.ai](https://docs.dstack.ai).

## Help

dstack is still under development.  If you encounter bugs, please report them directly 
to the [issue tracker](https://github.com/dstackai/dstack/issues).
For bugs, be sure to specify the detailed steps to reproduce the issue.

For questions and support, join the [Slack chat](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

## Limitations and roadmap

Below is the list of existing limitations:

- **Visual dashboard:** There's no visual dashboard to manage repos, runs, tags, and secrets. 
  It's already in work and is going to be released shortly (Q3, 2022).
- **Interactive logs:** Currently, output logs of workflows are not interactive. Means, you can't 
  use output to display progress (e.g. via `tqdm`, etc.) Until it's supported, it's recommended that 
  you report progress via TensorBoard event files or hosted experiment trackers (e.g. WanB, Comet, 
  Neptune, etc.) 
- **Git:** Currently, dstack can be used only with GitHub repositories. If you'd like to use
  dstack with other Git hosting providers or without using Git at all, add or upvote the 
  corresponding issue.
- **Cloud :** dstack currently works only with AWS. If you'd like to use dstack with GCP, 
  Azure, or Kubernetes, add or upvote the corresponding issue.
- **Integrations:** Currently, dstack supports only basic providers. Advanced providers (e.g. for 
  distributed training and data processing) are going to be added later.

##  Licence

[Mozilla Public License 2.0](LICENSE.md)