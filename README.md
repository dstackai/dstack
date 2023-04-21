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
Automate your ML workflows
</h4>

<p align="center">
The easiest way to run ML workflows, provision infrastructure, create dev environments, run apps, and manage data. 
</p>

[![Slack](https://img.shields.io/badge/slack-join%20chat-blueviolet?logo=slack&style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

<p align="center">
<a href="https://dstack.ai/quickstart" target="_blank"><b>Quickstart</b></a> • 
<a href="https://dstack.ai/docs" target="_blank"><b>Docs</b></a> • 
<a href="https://dstack.ai/tutorials/dolly" target="_blank"><b>Tutorials</b></a> •
<a href="https://dstack.ai/blog" target="_blank"><b>Blog</b></a>
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

</div>

## What is dstack?

`dstack` is an open-source tool that makes it very easy to run ML workflows, provision
infrastructure, create dev environments, run apps, manage data, and track compute.

Ideal for processing data, training and fine-tuning models, running apps, and everything
                    in between the ML development process.

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

Choose [`hub`](https://docs.dstack.ai/installation/hub.md) if you prefer managing cloud credentials and settings through a user
interface while working in a team.

For running remote workflows with local cloud credentials, select [`aws`](https://docs.dstack.ai/installation/aws.md)
or [`gcp`](https://docs.dstack.ai/installation/gcp.md).

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

## More information

For additional information and examples, see the following links:

* [Quickstart](https://dstack.ai/docs/quickstart)
* [Docs](https://dstack.ai/docs)
* [Tutorials](https://dstack.ai/tutorials/dolly)
* [Blog](https://dstack.ai/blog)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)