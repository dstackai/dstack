<div align="center">
<h1 align="center">
  <a target="_blank" href="https://dstack.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo-dark.svg"/>
      <img alt="dstack" src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="400px"/>
    </picture>
  </a>
</h1>

<h3 align="center">
Reproducible ML workflows for teams
</h3>

<p align="center">
<code>dstack</code> helps teams run ML workflow in a configured cloud, manage dependencies, and version data.
</p>

[![Slack](https://img.shields.io/badge/slack-chat%20with%20us-blueviolet?logo=slack&style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

<p align="center">
<a href="https://docs.dstack.ai" target="_blank"><b>Docs</b></a> • 
<a href="https://docs.dstack.ai/examples" target="_blank"><b>Examples</b></a> • 
<a href="https://docs.dstack.ai/tutorials/quickstart"><b>Quickstart</b></a> • 
<a href="https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ" target="_blank"><b>Slack</b></a> • 
<a href="https://twitter.com/dstackai" target="_blank"><b>Twitter</b></a>
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

</div>

### Features

* **Workflows as code:** Define your ML workflows as code, and run them in a configured cloud via the command-line.
* **Reusable artifacts:** Save data, models, and environment as workflows artifacts, and reuse them across projects.
* **Built-in containers:** Workflow containers are pre-built with Conda, Python, etc. No Docker is needed.

> You can use the `dstack` CLI from both your IDE and your CI/CD pipelines.
> 
> For debugging purposes, you can run workflow locally, or attach to them interactive dev environments (e.g. VS Code, 
and JupyterLab).

## How does it work?

1. Install `dstack` CLI locally 
2. Configure the cloud credentials locally (e.g. via `~/.aws/credentials`)
3. Define ML workflows in `.dstack/workflows.yaml` (within your existing Git repository)
4. Run ML workflows via the `dstack run` CLI command
5. Use other `dstack` CLI commands to manage runs, artifacts, etc.

When you run a workflow via the `dstack` CLI, it provisions the required compute resources (in a configured cloud
account), sets up environment (such as Python, Conda, CUDA, etc), fetches your code, downloads deps,
saves artifacts, and tears down compute resources.

### Demo

<video src="https://user-images.githubusercontent.com/54148038/203490366-e32ef5bb-e134-4562-bf48-358ade41a225.mp4" controls="controls" style="max-width: 800px;"> 
</video>

## Installation

Use pip to install `dstack` locally:

```shell
pip install dstack
```

The `dstack` CLI needs your AWS account credentials to be configured locally.
(e.g. in `~/.aws/credentials` or `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables).

Before you can use the `dstack` CLI, you need to configure it:

```shell
dstack config
```

It will prompt you to select an AWS region 
where `dstack` will provision compute resources, and an S3 bucket, 
where dstack will store state and output artifacts.

```shell
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

## Usage example

**Step 1:** Create a `.dstack/workflows.yaml` file, and define there how to run the script, 
from where to load the data, how to store output artifacts, and what compute resources are
needed to run it.

```yaml
workflows:
  - name: download
    help: "Download the MNIST dataset"
    provider: bash
    commands:
      - pip install -r requirements.txt
      - python mnist/download.py
    artifacts:
      - path: data

  - name: train
    help: "Train a MNIST model"
    deps:
      - tag: mnist_data
    provider: bash
    commands:
      - pip install -r requirements.txt
      - python mnist/train.py
    artifacts:
      - path: lightning_logs
```

Use `deps` to add artifacts of other workflows as dependencies. You can refer to other 
workflows via the name of the workflow, or via the name of the tag. 

**Step 2:** Init repo
Before you can use dstack on a new Git repo, you have to run the dstack init command:

```shell
dstack init
```
It will ensure that dstack has the access to the Git repo.


**Step 3:** Run download workflow and command to see the status of runs.
Now, you can use the dstack run command to run the download workflow:

```shell
dstack run download
```
- Note: Add `-l` flag to run your workflow locally (instead of provisioning infrastructure in the cloud)

When you run a workflow, the CLI provisions infrastructure, prepares environment, fetches your code, etc.
Once the workflow is finished, its artifacts are saved and infrastructure is torn down.

```shell
dstack ps
dstack artifacts list <artifact-name>
```

**Step 4:** Add tag:
```shell
dstack tags add mnist_data <artifact-name>
```

**Step 5:** Run train workflow:
```shell
dstack run train
```
It will automatically provision the required compute resource, and run the workflow. You'll see the output in real-time:

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

**Step 6:** Download artifacts:
```shell
dstack artifacts download <artifact-name> .
```

**Step 7:** Use other commands to manage runs, artifacts, tags, secrets, and more.

## More information

 * [Docs](https://docs.dstack.ai/tutorials/quickstart)
 * [Examples](https://docs.dstack.ai/examples)
 * [Quickstart](https://docs.dstack.ai/tutorials/quickstart) 
 * [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
 * [Newsletter](https://dstack.curated.co/)
 * [Twitter](https://twitter.com/dstackai)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)