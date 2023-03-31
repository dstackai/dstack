---
title: A better way to run ML workflows
hide:
  - path
---

# A better way to run ML workflows

Welcome to `dstack`'s documentation! Here you can learn what it is, how it works, and how to get started.


## What is dstack?

`dstack` allows you to define machine learning workflows as code and run them on any cloud. 

It helps you set up a reproducible environment, reuse artifacts, and launch interactive development environments and apps.

[Get started](installation.md){ class="md-go-to-action primary" } [Join Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ){ class="md-go-to-action secondary slack" }

## Define workflows

Define ML workflows, their output artifacts, hardware requirements, and dependencies via YAML.

<div editor-title=".dstack/workflows/mnist.yaml"> 

```yaml
workflows:
  - name: mnist-data
    provider: bash
    commands:
      - pip install torchvision
      - python tutorials/mnist/mnist_data.py
    artifacts:
      - path: ./data

  - name: train-mnist
    provider: bash
    deps:
      - workflow: mnist-data
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - python tutorials/mnist/train_mnist.py
    artifacts:
      - path: ./lightning_logs
```

</div>

With YAML, you can avoid making changes to your scripts and have the freedom to use any frameworks, experiment trackers,
or cloud providers.

### Providers

`dstack` supports multiple [providers](usage/providers.md) that enable you to set up environment, run scripts, launch interactive dev environments and apps, and perform many other tasks.

## Run workflows

Once a workflow is defined, you can use the `dstack run` command to run it either locally or remotely. 

### Run locally

By default, workflows run locally on your machine:

<div class="termy">

```shell
$ dstack run mnist-data

RUN        WORKFLOW    SUBMITTED  STATUS     TAG  BACKENDS
penguin-1  mnist-data  now        Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Downloading http://yann.lecun.com/exdb/mnist/train-images-idx3-ubyte.gz
---> 100%

$ 
```

</div>

The artifacts from local workflows are also stored and can be reused in other local workflows.

### Run remotelly

To run a workflow remotely (e.g. in a configured cloud account), add the `--remote` flag to the `dstack run` command:

<div class="termy">

```shell
$ dstack run mnist-data --remote

RUN        WORKFLOW    SUBMITTED  STATUS     TAG  BACKENDS
mangust-1  mnist-data  now        Submitted       aws

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Downloading http://yann.lecun.com/exdb/mnist/train-images-idx3-ubyte.gz
---> 100%

$ 
```

</div>

The output artifacts from remote workflows are also stored remotely and can be reused by other remote workflows.

#### Resources

You can request the necessary hardware resources either through arguments in the `dstack run` command (such
as `--gpu` and `--gpu-name`) or via [YAML](reference/providers/bash.md#resources).

<div class="termy">

```shell
$ dstack run train-mnist --remote --gpu 1

RUN       WORKFLOW     SUBMITTED  STATUS     TAG  BACKENDS
turtle-1  train-mnist  now        Submitted       aws

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

GPU available: True, used: True

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
---> 100%

$ 
```

</div>

When you run a workflow remotely, `dstack` automatically creates resources in the configured cloud account
and then destroys them once the workflow is complete.

#### Ports

When a workflow uses ports to host interactive dev environments or applications, the `dstack run` command automatically
forwards these ports to your local machine, allowing you to access them. 
Refer to [Providers](usage/providers.md) and [Apps](usage/apps.md) for the details.

## Community

Join our community by connecting with
us on our [Slack channel](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
and [GitHub](https://github.com/dstackai/dstack) repository.