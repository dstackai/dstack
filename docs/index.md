---
title: Reproducible ML workflows for teams 
---

# Reproducible ML workflows for teams

## Welcome to dstack

`dstack` helps teams run ML workflow in a configured cloud, manage dependencies, and version data.

### Features

* **Workflows as code:** Define your ML workflows as code, and run them in a configured cloud via the command-line.
* **Reusable artifacts:** Save data, models, and environment as workflows artifacts, and reuse them across projects.
* **Built-in containers:** Workflow containers are pre-built with Conda, Python, etc. No Docker is needed.

!!! info "NOTE:"
    You can use the `dstack` CLI from both your IDE and your CI/CD pipelines.

    For debugging purposes, you can run workflow locally, or attach to them interactive dev environments (e.g. VS Code, 
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

<iframe src="https://user-images.githubusercontent.com/54148038/203490366-e32ef5bb-e134-4562-bf48-358ade41a225.mp4" allowfullscreen width="800" height="420" frameborder="0" allow="autoplay"></iframe>

## Get started in 30 min

Set your first ML workflows up and running should take 30 min or less.

<div class="grid cards" markdown>
- [**1. Explore examples**
   Browse the featured examples of what you can do with `dstack`.](examples)
- [**2. Install the CLI** 
   Install and configure the `dstack` CLI in no time.](installation.md)
- [**3. Follow quickstart**
   Try `dstack` yourself by following a simple step-by-step tutorial.](tutorials/quickstart.md)
- [**4. Join our community**
   Join our Slack chat to get support and hear about announcements.
  ](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
</div>

Subscribe to the [newsletter](https://dstack.curated.co/) to get notified about new updates.