<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="500px"/>    

______________________________________________________________________

[![PyPI](https://img.shields.io/github/workflow/status/dstackai/dstack/Build?style=flat-square)](https://github.com/dstackai/dstack/actions/workflows/build.yml)
[![PyPI](https://img.shields.io/pypi/v/dstack?style=flat-square&color=blueviolet)](https://pypi.org/project/dstack/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat-square&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

#### [Docs](https://docs.dstack.ai) - [Quickstart](https://docs.dstack.ai/tutorials/quickstart) - [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ) - [Twitter](https://twitter.com/dstackai)

</div>

`dstack` is a lightweight command-line utility that lets you run ML workflows in the cloud,
while keeping them highly reproducible.

## Features

 * Define your ML workflows declaratively, incl. their dependencies, environment, and required compute resources 
 * Run workflows via the `dstack` CLI. Have infrastructure provisioned automatically in a configured cloud account. 
 * Save output artifacts, such as data and models, to reuse them in other ML workflows

## Demo

<img src="https://s4.gifyu.com/images/dstack-run-gpu.gif" width="800px"/>

## How does it work?

1. Install `dstack` locally 
2. Define ML workflows in `.dstack/workflows.yaml` (within your existing Git repository)
3. Run ML workflows via the `dstack run` CLI command
4. Use other `dstack` CLI commands to manage runs, artifacts, etc.

>  When you run an ML workflow via the `dstack` CLI, it provisions the required compute resources (in a configured cloud
   account), sets up environment (such as Python, Conda, CUDA, etc), fetches your code, downloads deps,
   saves artifacts, and tears down compute resources.

## Installation

Use pip to install `dstack` locally:

```shell
pip install dstack
```

The `dstack` CLI needs your AWS account credentials to be configured locally 
(e.g. in `~/.aws/credentials` or `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables).

Before you can use the `dstack` CLI, you need to configure it:

```shell
dstack config
```

It will prompt you to select the AWS region 
where dstack will provision compute resources, and the S3 bucket, where dstack will save data.

```shell
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

> Support for GCP and Azure is in the roadmap.

## Usage example

Say, you have a Python script that trains a model. It loads data from a local folder and saves the checkpoints
into another folder.

Now, to make it possible to run it via dstack, you have to create a `.dstack/workflows.yaml` file, and define there
how to run the script, where to load the data, how to store output artifacts, and what compute resources are
needed to run it.

```yaml
workflows: 
  - name: train
    provider: bash
    deps:
      - tag: mnist_data
    commands:
      - pip install requirements.txt
      - python src/train.py
    artifacts: 
      - path: checkpoint
    resources:
      interruptible: true
      gpu: 1
```

Now you can run it via the `dstack` CLI:

```shell
dstack run train
```

You'll see the output in real-time as your workflow is running.

```shell
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Epoch 4: 100%|██████████████| 1876/1876 [00:17<00:00, 107.85it/s, loss=0.0944, v_num=0, val_loss=0.108, val_acc=0.968]

`Trainer.fit` stopped: `max_epochs=5` reached.

Testing DataLoader 0: 100%|██████████████| 313/313 [00:00<00:00, 589.34it/s]

Test metric   DataLoader 0
val_acc       0.965399980545044
val_loss      0.10975822806358337
```

Use the `dstack ps` command to see the status of recent workflows.

```shell
dstack ps -a

RUN               TARGET    SUBMITTED    OWNER           STATUS   TAG
angry-elephant-1  download  8 hours ago  peterschmidt85  Done     mnist_data
wet-insect-1      train     1 weeks ago  peterschmidt85  Running  
```

Other CLI commands allow to manage runs, artifacts, tags, secrets, and more.

You can use dstack to not only process data or train models, but also to run applications,
and dev environments.

> All the state and output artifacts are stored in a configured S3 bucket.

## More information

 * [Documentation](https://docs.dstack.ai)
 * [GitHub Issues](https://github.com/dstackai/dstack/issues)
 * [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
 * [Blog](https://mlopsfluff.dstack.ai/)
 * [Twitter](https://twitter.com/dstackai)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)