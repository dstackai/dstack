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
A better way to run ML workflows
</h4>

<p align="center">
Define ML workflows as code and run via CLI. Use any cloud. Collaborate within teams. 
</p>

[![Slack](https://img.shields.io/badge/slack-join%20community-blueviolet?logo=slack&style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

<p align="center">
<a href="https://docs.dstack.ai" target="_blank"><b>Docs</b></a> • 
<a href="https://docs.dstack.ai/installation"><b>Installation</b></a> • 
<a href="https://docs.dstack.ai/quick-start"><b>Quick start</b></a> • 
<a href="https://docs.dstack.ai/usage/hello-world" target="_blank"><b>Usage</b></a> 
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

</div>

## What is dstack?

`dstack` allows you to define machine learning workflows as code and run them on any cloud. 

It helps you set up a reproducible environment, reuse artifacts, and launch interactive development environments and apps.

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
  [hub]
```

If you intend to run remote workflows directly in the cloud using local cloud credentials, 
feel free to choose `aws` or `gcp`. Refer to [AWS](#aws) and [GCP](#gcp) correspondingly for the details.

If you would like to manage cloud credentials, users and other settings centrally
via a user interface, it is recommended to choose `hub`. 

> The `hub` remote is currently in an experimental phase. If you are interested in trying it out, please contact us 
> via [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

## Define workflows

Define ML workflows, their output artifacts, hardware requirements, and dependencies via YAML.

```yaml
workflows:
  - name: mnist-data
    provider: bash
    commands:
      - pip install torchvision
      - python mnist/mnist_data.py
    artifacts:
      - path: ./data

  - name: train-mnist
    provider: bash
    deps:
      - workflow: mnist-data
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - python mnist/train_mnist.py
    artifacts:
      - path: ./lightning_logs
```

YAML eliminates the need to modify code in your scripts, giving you the freedom to choose frameworks,
experiment trackers, and cloud providers.

### Providers

`dstack` supports multiple [providers](https://docs.dstack.ai/usage/providers.md) that enable you to set up environment,
run scripts, launch interactive dev environments and apps, and perform many other tasks.

## Run workflows

Once a workflow is defined, you can use the `dstack run` command to run it either locally or remotely. 

### Run locally

By default, workflows run locally on your machine.

```shell
dstack run mnist-data

RUN        WORKFLOW    SUBMITTED  STATUS     TAG  BACKENDS
penguin-1  mnist-data  now        Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Downloading http://yann.lecun.com/exdb/mnist/train-images-idx3-ubyte.gz
```

The artifacts from local workflows are also stored and can be reused in other local workflows.

### Run remotely

To run a workflow remotely (e.g. in a configured cloud account), add the `--remote` flag to the `dstack run` command:

```shell
dstack run mnist-data --remote

RUN        WORKFLOW    SUBMITTED  STATUS     TAG  BACKENDS
mangust-1  mnist-data  now        Submitted       aws

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Downloading http://yann.lecun.com/exdb/mnist/train-images-idx3-ubyte.gz
```

The output artifacts from remote workflows are also stored remotely and can be reused by other remote workflows.

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

#### Ports

When a workflow uses ports to host interactive dev environments or applications, the `dstack run` command automatically
forwards these ports to your local machine, allowing you to access them. 
Refer to [Providers](usage/providers.md) and [Apps](usage/apps.md) for the details.

## More information

For additional information and examples, see the following links:

* [Docs](https://docs.dstack.ai/)
* [Installation](https://docs.dstack.ai/installation)
* [Quick start](https://docs.dstack.ai/quick-start)
* [Usage](https://docs.dstack.ai/usage/hello-world)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)