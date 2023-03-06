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
Easy-to-run ML workflows on any cloud
</h4>

<p align="center">
Define ML workflows as code and run via CLI. Use any cloud. Collaborate within teams. 
</p>

[![Slack](https://img.shields.io/badge/slack-join%20community-blueviolet?logo=slack&style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

<p align="center">
<a href="https://docs.dstack.ai" target="_blank"><b>Docs</b></a> • 
<a href="https://docs.dstack.ai/quick-start"><b>Quick start</b></a> • 
<a href="https://docs.dstack.ai/basics/hello-world" target="_blank"><b>Basics</b></a> • 
<a href="https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ" target="_blank"><b>Slack</b></a> 
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

</div>

`dstack` is the most easy way to define ML workflows as code and run them either locally or remotely on any cloud.

### Highlighted features

* Define ML workflows declaratively as code
* Run workflows locally or remotely on any cloud (AWS, GCP, etc)
* Use on-demand on spot instances conveniently
* Save data, checkpoints, environments as artifacts and reuse them across workflows
* No need to use custom Docker images or Kubernetes

## Installation

Use pip to install the `dstack` CLI:

```shell
pip install dstack --upgrade
```

## Example

Here's an example from the [Quick start](https://docs.dstack.ai/quick-start).

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

YAML-defined workflows eliminate the need to modify code in your scripts, giving you the freedom to choose frameworks,
experiment trackers, and cloud providers.

## Run locally

Use the `dstack` CLI to run workflows locally:

```shell
dstack run mnist-data
```

## Run remotely

To run workflows remotely (e.g. in the cloud) or share artifacts outside your machine, 
you must configure your remote settings using the `dstack config` command:

```shell
dstack config
```

This command will ask you to choose the type of backend (e.g. AWS), and the corresponding
settings (e.g. the region where to run workflows, an S3 bucket where to store artifacts, etc).

```shell
Backend: aws
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

For more details on how to configure a remote, check the [installation](https://docs.dstack.ai/installation/#configure-a-remote) guide.

Once a remote is configured, use the `--remote` flag with the `dstack run` command to run the 
workflow in the configured cloud:

```shell
dstack run mnist-data --remote
```

You can configure the required resources to run the workflows either via the `resources` property in YAML
or the `dstack run` command's arguments, such as `--gpu`, `--gpu-name`, etc:

```shell
dstack run train-mnist --remote --gpu 1
```

When you run a workflow remotely, `dstack` automatically creates resources in the configured cloud,
and releases them once the workflow is finished.

## More information

For additional information and examples, see the following links:

* [Docs](https://docs.dstack.ai/)
* [Installation](https://docs.dstack.ai/installation)
* [Quick start](https://docs.dstack.ai/quick-start)
* [Basics](https://docs.dstack.ai/basics/hello-world)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)