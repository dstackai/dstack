---
title: Easy-to-run ML workflows on any cloud
#hide:
#  - footer
---

# Easy-to-run ML workflows on any cloud

Welcome to `dstack`'s documentation! Here you can learn what it is, how it works, and how to get started.

## What is dstack?

`dstack` is an open-source tool that enables defining ML workflows as code, running them easily on any cloud while saving
artifacts for reuse. It offers freedom to use any ML frameworks, cloud vendors, or third-party tools without requiring
code changes.

[Get started](installation.md){ class="md-go-to-action primary" } [Join our Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ){ class="md-go-to-action secondary slack" }

## How does it work?

### Define workflows

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

YAML eliminates the need to modify code in your scripts, giving you the freedom to choose frameworks,
experiment trackers, and cloud providers.

### Run workflows

Once a workflow is defined, you can use the `dstack run` command to run it either locally or remotely. 

#### Run locally

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

#### Run remotely

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

The necessary hardware resources can be configured either via YAML or through arguments in the `dstack run` command, such
as `--gpu` and `--gpu-name`.

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

Upon running a workflow remotely, `dstack` automatically creates resources in the configured cloud account and destroys them
once the workflow is complete.

!!! info "NOTE:"
    For questions or feedback, reach us through
    our [community Slack channel](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
    or [GitHub](https://github.com/dstackai/dstack).