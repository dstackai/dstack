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
The easiest way to run ML workflows
</h4>

<p align="center">
Define ML workflows as code and run via CLI. Use any cloud. Collaborate within teams. 
</p>

[![Slack](https://img.shields.io/badge/slack-join%20chat-blueviolet?logo=slack&style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

<p align="center">
<a href="https://docs.dstack.ai" target="_blank"><b>Docs</b></a> • 
<a href="https://docs.dstack.ai/installation"><b>Installation</b></a> • 
<a href="https://docs.dstack.ai/quick-start"><b>Quick start</b></a> • 
<a href="https://docs.dstack.ai/playground" target="_blank"><b>Playground</b></a> •   
<a href="https://docs.dstack.ai/usage/hello-world" target="_blank"><b>Usage</b></a>  • 
<a href="https://docs.dstack.ai/examples/tensorboard" target="_blank"><b>Examples</b></a>
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

</div>

## What is dstack?

`dstack` is an open-source tool makes it very easy to run ML workflows anywhere (whether it be on a local machine or on any cloud platform). collaboration.

## Installation

Use `pip` to install `dstack`:

```shell
pip install dstack --upgrade
```

## Configure a remote

To run workflows remotely (e.g. in a configured cloud account),
configure a remote using the `dstack config` command.

```shell
dstack config

? Choose backend. Use arrows to move, type to filter
> [aws]
  [gcp]
```

If you intend to run remote workflows directly in the cloud using local cloud credentials, 
feel free to choose `aws` or `gcp`. Refer to [AWS](#aws) and [GCP](#gcp) correspondingly for the details.

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
    cache:
      - path: ./data
      - path: ~/.cache/pip
```

The workflow instructs `dstack` how to execute it, which folders to save as artifacts for later use, which folders to cache between
runs, the dependencies it has on other workflows, the ports to open, and so on.

## Run workflows

Once a workflow is defined, you can use the `dstack run` command to run it either locally or remotely. 

### Run locally

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

### Run remotely

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

### Providers

`dstack` supports multiple [providers](https://docs.dstack.ai/usage/providers.md) that enable you to set up environment,
run scripts, launch interactive dev environments and apps, and perform many other tasks.

## More information

For additional information and examples, see the following links:

* [Docs](https://docs.dstack.ai/)
* [Installation](https://docs.dstack.ai/installation)
* [Quick start](https://docs.dstack.ai/quick-start)
* [Playground](https://github.com/dstackai/dstack-playground)
* [Usage](https://docs.dstack.ai/usage/hello-world)
* [Examples](https://docs.dstack.ai/examples/tensorboard)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)