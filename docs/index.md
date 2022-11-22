---
title: Reproducible ML workflows 
---

# Welcome to dstack

## Introduction

`dstack` is an open-source tool that helps teams define ML workflow, and
run them in a configured cloud. It takes care of 
provisioning compute resources, handling dependencies, and versioning data.
You can use the `dstack` CLI from both your IDE and your CI/CD pipelines.

<iframe src="https://player.vimeo.com/video/766452681?h=6e954feb34&amp;title=0&amp;byline=0&amp;portrait=0&amp;speed=0&amp;badge=0&amp;autopause=0&amp;player_id=0&amp;app_id=56727" width="800" height="420" frameborder="0" allow="autoplay" title="test"></iframe>

### Features

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

## Next steps

<div class="grid cards" markdown>
- [**Installation** 
   See how to install and configure `dstack` locally.](installation.md)
- [**Quickstart**
   Try `dstack` yourself by following a step-by-step tutorial.](tutorials/quickstart.md)
- [**Examples**
   Check basic examples of how to use `dstack`.](examples/hello)
- [**Community**
   Join our Slack for support and to talk to other users of `dstack`.
  ](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
</div>