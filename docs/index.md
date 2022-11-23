---
title: Reproducible ML workflows for teams 
---

# Reproducible ML workflows for teams

## Welcome to dstack

`dstack` helps teams define ML workflow, run them in a configured cloud, and collaborate around artifacts.
It takes care of provisioning compute resources, handling dependencies, and versioning data.

### Features

* Define your ML workflows declaratively (incl. their dependencies, environment, artifacts, and compute resources).
* Run workflows via the CLI. Have compute resources provisioned in your cloud (using your local credentials). 
* Save data, models, and environments as artifacts and reuse them across workflows and teams. 

You can use the `dstack` CLI from both your IDE and your CI/CD pipelines.

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

<iframe src="https://user-images.githubusercontent.com/54148038/203490366-e32ef5bb-e134-4562-bf48-358ade41a225.mp4" allowfullscreen width="800" height="420" frameborder="0" allow="autoplay"></iframe>

## Next steps

<div class="grid cards" markdown>
- [**Installation** 
   See how to install and configure `dstack` locally.](installation.md)
- [**Quickstart**
   Try `dstack` yourself by following a simple step-by-step tutorial.](tutorials/quickstart.md)
- [**Examples**
   Check basic examples of what `dstack` can do.](examples)
- [**Community**
   Join our Slack chat to get support and hear about announcements.
  ](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
</div>