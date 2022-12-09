---
title: Reproducible ML workflows for teams 
---

# Reproducible ML workflows for teams

## Introduction to dstack

`dstack` allows you define ML workflows as code, and run then in a configured cloud via the CLI. 
It automatically handles workflow dependencies, provisions cloud infrastructure, and versions 
data, models, and environments.

### Features

* **GitOps-driven:** Define your ML workflows via YAML, and run them in a configured cloud using the CLI, &mdash; 
  interactively from the IDE or from your CI/CD pipeline.
* **Collaborative:** Version data, models, and environments, and reuse them easily in other workflows &mdash; 
  across different projects and teams.
* **Cloud-native:** Run workflows locally or in a configured cloud.
  Configure the resources required by workflows (memory, GPU, etc.) as code.
* **Vendor-agnostic:** Use any cloud provider, languages, frameworks, tools, and third-party services. No code changes
  is required.
* **Dev environments:** For debugging purposes, attach interactive dev environments (e.g. VS Code, JupyterLab, etc.)
  directly to running workflows.

## Why use dstack?

`dstack` is the easiest and most flexible way for teams to automate ML workflows.

Are you exploring or preparing data? Training and validating models? Running apps?
Versioning and reusing artifacts? All of that is covered by `dstack`.

## How does it work?

1. Install `dstack` CLI locally 
2. Configure the cloud credentials locally (e.g. via `~/.aws/credentials`)
3. Define ML workflows in YAML files inside the `.dstack/workflows` directory (within your project)
4. Run ML workflows via the `dstack run` CLI command
5. Use other `dstack` CLI commands to manage runs, artifacts, etc.

!!! info "NOTE:"
    When you run a workflow via the `dstack` CLI, it provisions the required compute resources (in a configured cloud
    account), sets up environment (such as Python, Conda, CUDA, etc), fetches your code, downloads dependencies,
    saves artifacts, and tears down compute resources.

### Demo

<iframe src="https://user-images.githubusercontent.com/54148038/203490366-e32ef5bb-e134-4562-bf48-358ade41a225.mp4" allowfullscreen width="800" height="420" frameborder="0" allow="autoplay"></iframe>

### Get started in 30 min

Having your first ML workflows up and running will take less than 30 min.

<div class="grid cards" markdown>
- [**1. Examples**
   Browse the featured examples of what you can do with `dstack`.](examples)

[//]: # (- [**2. Installation** )
[//]: # (   Install and configure the `dstack` CLI in no time.]&#40;installation.md&#41;)

- [**3. Quickstart**
   Try `dstack` yourself by following a simple step-by-step tutorial.](tutorials/quickstart.md)

- [//]: # (- [**4. Slack**)
[//]: # (   Join our Slack chat to get support and hear about announcements.)
[//]: # (  ]&#40;https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ&#41;)
</div>