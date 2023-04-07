---
title: Universal ML workflows as code
hide:
  - path
---

# Universal ML workflows as code

`dstack` is an open-source tool makes it very easy to run ML workflows anywhere (whether it be on a local machine or on any cloud platform).

[Quick start](quick-start.md){ class="md-go-to-action primary" } [:video_game: Playground](playground.md){ class="md-go-to-action secondary" }

## Define workflows

Define ML workflows, their output artifacts, hardware requirements, and dependencies via YAML.

<div editor-title=".dstack/workflows/mnist.yaml"> 

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

</div>

## Run locally

Once a workflow is defined, you can use the `dstack run` command to run it. 

By default, workflows run locally on your machine:

<div class="termy">

```shell
$ dstack run train-mnist

RUN        WORKFLOW     SUBMITTED  STATUS     TAG  BACKENDS
penguin-1  train-mnist  now        Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

GPU available: False, used: False

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
---> 100%
```

</div>

## Run remotely

To run a workflow remotely (e.g. in a configured cloud account), add the `--remote` flag to the `dstack run` command:

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
```

</div>

Upon running a workflow remotely, `dstack` automatically creates resources in the configured cloud account and destroys them
once the workflow is complete.

## Providers

`dstack` supports multiple [providers](usage/providers.md) that enable you to set up environment,
run scripts, launch interactive dev environments and apps, and perform many other tasks.
