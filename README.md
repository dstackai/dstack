<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="300px"/>    

Git-based CLI to run ML workflows on cloud
______________________________________________________________________

![PyPI](https://img.shields.io/github/workflow/status/dstackai/dstack/Build?logo=github&style=for-the-badge)
[![PyPI](https://img.shields.io/pypi/v/dstack?style=for-the-badge)](https://pypi.org/project/dstack/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=for-the-badge)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
[![Slack](https://img.shields.io/badge/slack-join-e01563?style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

[//]: # ([![twitter]&#40;https://img.shields.io/twitter/follow/dstackai.svg?style=social&label=Follow&#41;]&#40;https://twitter.com/dstackai&#41;)

</div>

## 👋 Intro

To run ML workflows, your local machine is often not enough. 
That’s why you often have to automate running ML workflows withing the cloud infrastructure.

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
5. **Technology-agnostic:** No need to use specific APIs in your code. Anything that works locally, can run via dstack.
6. **Dev environments:** Workflows may be not only tasks and applications but also dev environments, incl. 
   IDEs and notebooks.
7. **Very easy setup:** Install the dstack CLI and run workflows
   in the cloud using your local credentials. The state is stored in an S3 bucket. 
   No need to set up anything else.

## 📦 Installation

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

## ✨ Usage

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

#### Environment setup
    
dstack automatically sets up environment for the workflow. It pre-installs the right CUDA driver 
and Conda.

#### Git

When you run a workflow withing a Git repository, dstack detects the current branch, commit hash, 
and local changes, and uses it on the cloud instance(s) to run the workflow.

## Manage artifacts

Every workflow may have its output artifacts. If needed, artifacts can be read/written in real-time.

Artifacts can be accessed via the `dstack artifacts` CLI command.

## Manage tags

Tags help manage data.

For example, you can assign a tag to a finished workflow to use its output artifacts from other workflows.

Also, you can create a tag by uploading data from your local machine.

To make a workflow use the data via a tag, one has to use the `deps` property in `.dstack/workflows.yaml`.

Example:

```yaml
deps:
  - tag: mnist_data
```

You can refer to tags from other projects as well.

Tags can be managed via the `dstack tags` CLI command.

## Providers

dstack offers [multiple providers](https://docs.dstack.ai/providers) that allow running tasks, applications, 
and dev environments.

## 📘 Docs

More tutorials, examples, and the full CLI reference can be found at [docs.dstack.ai](https://docs.dstack.ai).

## 🛟 Help

If you encounter bugs, please report them directly 
to the [issue tracker](https://github.com/dstackai/dstack/issues).

For questions and support, join the [Slack chat](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

##  Licence

[Mozilla Public License 2.0](LICENSE.md)