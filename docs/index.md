---
title: A better way to run ML workflows
hide:
  - path
---

# The easiest way to run ML workflows

`dstack` is an open-source tool makes it very easy to run ML workflows anywhere (whether it be on a local machine or on any cloud platform).

[Quick start](quick-start.md){ class="md-go-to-action primary" } [:video_game: Playground](playground.md){ class="md-go-to-action secondary" }

## How it works?

Define ML workflows, their output artifacts, hardware requirements, and dependencies via YAML.

<div editor-title=".dstack/workflows/mnist.yaml"> 

```yaml
workflows:
  - name: mnist-data
    provider: bash
    commands:
      - pip install torchvision
      - python examples/mnist/mnist_data.py
    artifacts:
      - path: ./data

  - name: train-mnist
    provider: bash
    deps:
      - workflow: mnist-data
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - python examples/mnist/train_mnist.py
    artifacts:
      - path: ./lightning_logs
```

</div>

Once a workflow is defined, you can use the `dstack run` command to run it either locally or remotely. 

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
```

</div>

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

When you run a workflow remotely, `dstack` automatically creates resources in the configured cloud account
and then destroys them once the workflow is complete.