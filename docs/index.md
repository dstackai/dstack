---
title: Automate your ML workflows
hide:
  - path
---

# Automate your ML workflows

`dstack` is an open-source tool that automates ML workflows, enabling effective management on any cloud platform. It
empowers your team to explore and prepare data, train, and fine-tune models using their preferred frameworks and dev
environments without spending time on engineering and infrastructure.

[//]: # (`dstack` is designed with simplicity, developer productivity and ease of)
[//]: # (collaboration in mind.)

[//]: # (TODO: Dedicate a section or a page to features)

[Quick start](quick-start.md){ class="md-go-to-action primary" } [Playground](playground.md){ class="md-go-to-action secondary" }

## Get started in minutes

### Install the CLI

Use `pip` to install `dstack`:

<div class="termy">

```shell
$ pip install dstack
```

</div>

### Configure a remote

By default, workflows run locally. To run workflows remotely (e.g. in a configured cloud account),
configure a remote using the `dstack config` command.

<div class="termy">

```shell
$ dstack config
? Choose backend. Use arrows to move, type to filter
> [aws]
  [gcp]
  [hub]
```

</div>

To run remote workflows with local cloud credentials, choose [`aws`](setup/aws.md) or [`gcp`](setup/gcp.md). 

For managing cloud credentials securely and collaborate as a team, select [`hub`](setup/hub.md).

### Define workflows

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
```

</div>

### Run locally

By default, workflows run locally on your machine.

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

### Run remotely

To run a workflow remotely (e.g. in a configured cloud account), add the `--remote` flag to the `dstack run` command:

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
```

</div>

### Providers

`dstack` supports multiple providers to set up environments, run scripts, and launch interactive development environments and applications.

### Artifacts

`dstack` allows you to save output artifacts and conveniently reuse them across workflows.

### Try it now

Browse multiple examples and tutorial on how to use `dstack`.

[Playground](playground.md){ class="md-go-to-action primary" } [Tutorials](tutorials/tensorboard.md){ class="md-go-to-action secondary" }

