<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="300px"/>    

Git-based CLI to run ML workflows on cloud
______________________________________________________________________


[![PyPI](https://img.shields.io/github/workflow/status/dstackai/dstack/Build?style=for-the-badge)](https://github.com/dstackai/dstack/actions/workflows/build.yml)
[![PyPI](https://img.shields.io/pypi/v/dstack?style=for-the-badge)](https://pypi.org/project/dstack/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=for-the-badge&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

[Docs](https://docs.dstack.ai) | [Issues](https://github.com/dstackai/dstack/issues) | [Twitter](https://twitter.com/dstackai) | [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

</div>

## Intro

To run ML workflows, often your local machine is not enough. 
That’s why it's necessary to automate the process of running ML workflows within the cloud infrastructure.

Instead of managing infrastructure yourself, writing own scripts, or using cumbersome MLOps platforms, with dstack, 
you can focus on code while dstack does management of dependencies, infrastructure, and data for you.

dstack is an alternative to KubeFlow, SageMaker, Docker, SSH, custom scripts, and other tools used often to
run ML workflows.

### Primary features of dstack:

1. **Environment setup:** No need to use Docker, configure CUDA yourself, etc. Just specify workflow 
    requirements in your code, and it will be pre-configured.
2. **Data management:** Use tags to manage data and reuse it from workflows.
    Assign tags to finished workflows to reuse their artifacts from other workflows.
3. **Dev environments:** Workflows may include tasks, applications, also dev environments, such as 
    IDEs and Jupyter notebooks.
4. **Easy installation:** Just install the dstack CLI locally, and that's it.
    The CLI will use your local cloud credentials to run workflows. 
    The state is stored in an S3 bucket.
5. **Git-focused:** When you run a workflow, dstack detects your local branch, commit hash, and local changes, 
    and uses it to run the workflow in the cloud.
6. **Interruption-friendly:** Fully-leverage cloud spot/preemptive instances.
    If needed, store artifacts in real-time to resume workflows, e.g. if there were interrupted.

## Installation

To use dstack, you'll only need the dstack CLI. No other software needs to be installed or deployed.

The CLI will use your local cloud credentials (e.g. the default AWS environment variables 
or the credentials from `~/.aws/credentials`.)

In order to install the CLI, you need to use pip:

```shell
pip install dstack
```

Before you can use dstack, you have to configure the dstack backend:

 * In which S3 bucket, to store the state and the artifacts
 * In what region, to create cloud instances.

To configure this, run the following command:

```shell
dstack config
Configure AWS backend:

AWS profile name (default):
S3 bucket name:
Region name:
```

The configuration is stored in `~/.dstack/config.yaml`.

That's it. Now you can use dstack on your machine.

## Usage

### Define workflows

Workflows can be defined in the `.dstack/workflows.yaml` file within your 
project directory.

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

Once you run the workflow, dstack within a minute will create the required cloud instance(s), pre-configure
the environment, and run your workflow. You'll see the output in real-time as your 
workflow is running.

```shell
$ dstack run train

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

...
```

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

dstack is still under development. If you encounter bugs, please report them directly 
to [GitHub issues](https://github.com/dstackai/dstack/issues).
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
- **Git hosting providers:** Currently, dstack works only with the GitHub.com repositories. If you'd like to use
  dstack with other Git hosting providers (or without using Git at all), add or upvote the 
  corresponding issue.
- **Cloud providers:** dstack currently works only with AWS. If you'd like to use dstack with GCP, 
  Azure, or Kubernetes, add or upvote the corresponding issue.
- **Providers:** Advanced providers, e.g. for distributed training and data processing, are in plan.

##  Licence

[Mozilla Public License 2.0](LICENSE.md)