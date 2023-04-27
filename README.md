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
ML workflows as code
</h4>

<p align="center">
The easiest way to define ML workflows and run them on any cloud platform 
</p>

[![Slack](https://img.shields.io/badge/slack-join%20chat-blueviolet?logo=slack&style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

<p align="center">
<a href="https://dstack.ai/docs/quick-start" target="_blank"><b>Quick start</b></a> • 
<a href="https://dstack.ai/docs" target="_blank"><b>Docs</b></a> • 
<a href="https://dstack.ai/tutorials/dolly" target="_blank"><b>Tutorials</b></a> •
<a href="https://dstack.ai/blog" target="_blank"><b>Blog</b></a>
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

</div>

## What is dstack?

`dstack` makes it very easy to define ML workflows
and run them on any cloud platform. It provisions infrastructure,
manages data, and monitors usage for you.

Ideal for processing data, training models, running apps, and any other ML development tasks.

## Install the CLI

Use `pip` to install `dstack`:

```shell
pip install dstack
```

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

To run workflows remotely in a configured cloud, you will need the Hub application, which can be installed either on a
dedicated server for team work or directly on your local machine.

### Start the Hub application

To start the Hub application, use this command:

<div class="termy">

```shell
$ dstack hub start

The hub is available at http://127.0.0.1:3000?token=b934d226-e24a-4eab-a284-eb92b353b10f
```

</div>

To login as an administrator, visit the URL in the output.

### Create a project

Go ahead and create a new project.

<img src="https://dstack.ai/assets/dstack_hub_create_project.png" width="800px"/>

Choose a backend type (such as AWS or GCP), provide cloud credentials, and specify settings like
artifact storage bucket and the region where to run workflows.

<img src="https://dstack.ai/assets/dstack_hub_view_project.png" width="800px"/>

### Configure the CLI

Copy the CLI command from the project settings and execute it in your terminal to configure the project as a remote.

<div class="termy">

```shell
$ dstack config hub --url http://127.0.0.1:3000 \
  --project my-awesome-project \
  --token b934d226-e24a-4eab-a284-eb92b353b10f
```

</div>

Now, you can run workflows remotely in the created project by adding the `--remote` flag to the `dstack run` command
and request hardware [`resources`](usage/resources.md) (like GPU, memory, interruptible instances, etc.) that you need.

```shell
dstack run train-mnist --remote --gpu 1

RUN       WORKFLOW     SUBMITTED  STATUS     TAG  BACKENDS
turtle-1  train-mnist  now        Submitted       aws

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

GPU available: True, used: True

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
```

The command will automatically provision the required cloud resources in the corresponding cloud upon workflow 
startup and tear them down upon completion.

## More information

For additional information and examples, see the following links:

* [Quick start](https://dstack.ai/docs/quick-start)
* [Docs](https://dstack.ai/docs)
* [Tutorials](https://dstack.ai/tutorials/dolly)
* [Blog](https://dstack.ai/blog)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)