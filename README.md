<div align="center">
<h1 align="center">
  <a target="_blank" href="https://dstack.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo-dark.svg"/>
      <img alt="dstack" src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="400px"/>
    </picture>
  </a>
</h1>

<h4 align="center">
Automate your ML workflows on any cloud
</h4>

<p align="center">
The hassle-free tool for managing ML workflows on any cloud platform. 
</p>

[![Slack](https://img.shields.io/badge/slack-join%20chat-blueviolet?logo=slack&style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

<p align="center">
<a href="https://docs.dstack.ai" target="_blank"><b>Docs</b></a> • 
<a href="https://docs.dstack.ai/quick-start"><b>Quick start</b></a> • 
<a href="https://docs.dstack.ai/playground" target="_blank"><b>Playground</b></a> •   
<a href="https://docs.dstack.ai/setup"><b>Setup</b></a> • 
<a href="https://docs.dstack.ai/usage/hello-world" target="_blank"><b>Usage</b></a>  • 
<a href="https://docs.dstack.ai/examples/tensorboard" target="_blank"><b>Examples</b></a>
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

</div>

## What is dstack?

`dstack` is an open-source tool that automates ML workflows, enabling effective management on any cloud platform. 

It empowers your team to prepare data, train, and fine-tune models using their preferred frameworks and dev
environments without spending time on engineering and infrastructure.

## Install the CLI

Use `pip` to install `dstack`:

```shell
pip install dstack
```

## Configure a remote

By default, workflows run locally. To run workflows remotely (e.g. in a configured cloud account),
configure a remote using the `dstack config` command.

```shell
dstack config

? Choose backend. Use arrows to move, type to filter
> [aws]
  [gcp]
  [hub]
```

Choose [`hub`](https://docs.dstack.ai/setup/hub.md) if you prefer managing cloud credentials and settings through a user
interface while working in a team.

For running remote workflows with local cloud credentials, select [`aws`](https://docs.dstack.ai/setup/aws.md)
or [`gcp`](https://docs.dstack.ai/setup/gcp.md).

## Define workflows

Define ML workflows, their output artifacts, hardware requirements, and dependencies via YAML.

```yaml
workflows:
  - name: train-mnist
    provider: bash
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - python examples/mnist/train_mnist.py
    artifacts:
      - path: ./lightning_logs
```

## Run locally

By default, workflows run locally on your machine.

```shell
dstack run train-mnist

RUN        WORKFLOW     SUBMITTED  STATUS     TAG  BACKENDS
penguin-1  train-mnist  now        Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

GPU available: True, used: True

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
```

## Run remotely

To run a workflow remotely (e.g. in a configured cloud account), add the `--remote` flag to the `dstack run` command:

The necessary hardware resources can be configured either via YAML or through arguments in the `dstack run` command, such
as `--gpu` and `--gpu-name`.

```shell
dstack run train-mnist --remote --gpu 1

RUN       WORKFLOW     SUBMITTED  STATUS     TAG  BACKENDS
turtle-1  train-mnist  now        Submitted       aws

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

GPU available: True, used: True

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
```

Upon running a workflow remotely, `dstack` automatically creates resources in the configured cloud account and destroys them
once the workflow is complete.

## Providers

`dstack` supports multiple [providers](https://docs.dstack.ai/usage/providers) to set up environments, run scripts, and launch interactive development environments and applications.

## Artifacts

`dstack` allows you to save output artifacts and conveniently reuse them across workflows.

## More information

For additional information and examples, see the following links:

* [Docs](https://docs.dstack.ai/)
* [Quick start](https://docs.dstack.ai/quick-start)
* [Playground](https://github.com/dstackai/dstack-playground)
* [Setup](https://docs.dstack.ai/setup)
* [Usage](https://docs.dstack.ai/usage/hello-world)
* [Examples](https://docs.dstack.ai/examples/tensorboard)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)