<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="500px"/>    

______________________________________________________________________

[![PyPI](https://img.shields.io/github/workflow/status/dstackai/dstack/Build?style=flat-square)](https://github.com/dstackai/dstack/actions/workflows/build.yml)
[![PyPI](https://img.shields.io/pypi/v/dstack?style=flat-square&color=blueviolet)](https://pypi.org/project/dstack/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat-square&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

#### [Docs](https://docs.dstack.ai) - [Quickstart](https://docs.dstack.ai/tutorials/quickstart) - [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ) - [Twitter](https://twitter.com/dstackai)

</div>

`dstack` is an open-source tool that helps teams define ML workflow, and
run them in a configured cloud. It takes care of 
provisioning compute resources, handling dependencies, and versioning data.
You can use the `dstack` CLI from both your IDE and your CI/CD pipelines.

## Features

* Define your ML workflows declaratively (incl. their dependencies, environment, artifacts, and compute resources).
* Run workflows via the CLI. Have compute resources provisioned in your cloud (using your local credentials). 
* Save data, models, and environments as artifacts and reuse them across workflows and teams. 

For debugging purposes, you can spin dev environments (VS Code and JupyterLab), and also run workflow locally if needed.

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

<img src="https://s4.gifyu.com/images/dstack-run-gpu.gif" width="800px"/>

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
  - name: train
    provider: bash
    deps:
      - tag: mnist_data
    commands:
      - pip install requirements.txt
      - python src/train.py
    artifacts: 
      - path: ./checkpoint
    resources:
      interruptible: true
      gpu: 1
```

Use `deps` to add artifacts of other workflows as dependencies. You can refer to other 
workflows via the name of the workflow, or via the name of the tag. 

**Step 2:** Run the workflow via `dstack run`:

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

**Step 3:** Use the `dstack ps` command to see the status of runs.

```shell
dstack ps -a

RUN               TARGET    SUBMITTED    OWNER           STATUS   TAG
angry-elephant-1  download  8 hours ago  peterschmidt85  Done     mnist_data
wet-insect-1      train     1 weeks ago  peterschmidt85  Running  
```

**Step 4:** Use other commands to manage runs, artifacts, tags, secrets, and more.

## More information

 * [Docs](https://docs.dstack.ai)
 * [GitHub Issues](https://github.com/dstackai/dstack/issues)
 * [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
 * [Newsletter](https://dstack.curated.co/)
 * [Twitter](https://twitter.com/dstackai)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)