<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="300px"/>    

A command-line interface to run ML workflows in the cloud
______________________________________________________________________

![PyPI](https://img.shields.io/github/workflow/status/dstackai/dstack/Build?logo=github&style=for-the-badge)
[![PyPI](https://img.shields.io/pypi/v/dstack?style=for-the-badge)](https://pypi.org/project/dstack/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=for-the-badge)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
[![Slack](https://img.shields.io/badge/slack-join-e01563?style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

[//]: # ([![twitter]&#40;https://img.shields.io/twitter/follow/dstackai.svg?style=social&label=Follow&#41;]&#40;https://twitter.com/dstackai&#41;)

</div>

## 👋 Intro

To run ML workflows, your local machine is often not enough, so you need a way 
to automate running these workflows using the cloud infrastructure.

Instead of configuring cloud instances manually, writing custom scripts, or even using complicated MLOps platforms, 
now you can run workflows with a single dstack command.

dstack is an alternative to SSH, custom scripts, Docker, KubeFlow, SageMaker, and other tools used 
for running ML workflows.

### Primary features of dstack:

1. **Declarative workflows:** You define workflows within `./dstack/workflows.yaml` file 
  and run them via the CLI.
2. **Agnostic to tools and APIs:** No need to use specific APIs in your code. Anything that works locally, can run via dstack.
3. **Artifacts are the first-class citizens:** As you're running a workflow, artifacts are stored in real-time.
  If interrupted, resume from where it's stopped.
  Once the workflow is finished, assign a tag to it and reuse artifacts in other workflows.
4. **GitOps approach:** dstack is fully integrated with Git. Run workflows from the CLI. dstack tracks code automatically.
  No need to push your changes before running a workflow.
5. **Very easy setup:** No need to set up any complicated software. Just install the dstack CLI and run workflows
  in your cloud using your local credentials. The state is stored in your cloud storage. Work alone or collaborate within a team.

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
```

The configuration will be stored in `~/.dstack/config.yaml`:

```yaml
backend: aws
bucket: "my-dstack-workspace"
region: "eu-west-1"
```

That's it. Now you can use dstack in your machine.

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

### Run workflows

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

### Manage tags

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

### Manage artifacts

The artifacts command allows you to browse or download the contents of artifacts.

Here's how to browse artifacts:

```shell
dstack artifacts list (RUN | :TAG)
```

Here's how to download artifacts:

```shell
dstack artifacts download (RUN | :TAG) [OUTPUT_DIR]
```

## Providers

dstack offers [multiple providers](https://docs.dstack.ai/providers) that allow running various tasks, applications, 
and even dev environments.

## 📘 Docs

More tutorials, examples, and the full CLI reference can be found at [docs.dstack.ai](https://docs.dstack.ai).

## 🛟 Help

If you encounter bugs, please report them directly 
to the [issue tracker](https://github.com/dstackai/dstack/issues).

For questions and support, join the [Slack channel](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

##  Licence

[Mozilla Public License 2.0](LICENSE.md)