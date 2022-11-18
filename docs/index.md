---
title: Reproducible ML workflows 
---

# Reproducible ML workflows

## Introduction

`dstack` is a lightweight command-line utility that lets you run ML workflows in the cloud,
while keeping them highly reproducible.

<iframe src="https://player.vimeo.com/video/766452681?h=6e954feb34&amp;title=0&amp;byline=0&amp;portrait=0&amp;speed=0&amp;badge=0&amp;autopause=0&amp;player_id=0&amp;app_id=56727" width="800" height="420" frameborder="0" allow="autoplay" title="test"></iframe>

## What is dstack?

`dstack` is a lightweight command-line utility that lets you run ML workflows in the cloud,
while keeping them highly reproducible.

### Features

 * Define your ML workflows declaratively, incl. their dependencies, environment, and required compute resources 
 * Run workflows via the `dstack` CLI. Have infrastructure provisioned automatically in a configured cloud account. 
 * Save output artifacts, such as data and models, to reuse them in other ML workflows

### How does it work?

 * Install `dstack` locally (a simple `pip install` will do)
 * Configure the cloud credentials locally (e.g. via `~/.aws/credentials`)
 * Run `dstack config` to configure the cloud region (to provision infrastructure) and the S3 bucket (to store data)
 * Define ML workflows in `.dstack/workflows.yaml` (within your existing Git repository)
 * Run ML workflows via the `dstack run` CLI command. Use other CLI commands to show status, manage state, artifacts, etc. 

!!! tip "NOTE:"
    When you run an ML workflow via the `dstack` CLI, it provisions the required compute resources (in a configured cloud
    account), sets up environment (such as Python, Conda, CUDA, etc), fetches your code, downloads deps,
    saves artifacts, and tears down compute resources.

## Use cases

`dstack` is designed for AI researchers and ML engineers to simplify infrastructure provisioning in the cloud,
and drive the best engineering practices and collaboration. 

### Provisioning infrastructure

If your workflow, that processes data or trains a model, needs resources that you 
don't have locally (e.g. more GPU or memory), you can specify 
required hardware (via [`resources`](examples/index.md#resources)), and then run your workflows via 
[`dstack run`](reference/cli/run).

`dstack` will automatically create machines in the configured cloud account with required resources, 
and run your workflow.

### Utilizing spot instances 

To reduce costs, you can tell `dstack` to use 
interruptible instances (via [`interruptible`](examples/index.md#interruptible-instances)).

### Managing environment

When you run workflows via [`dstack run`](reference/cli/run), the container has already 
the right version of CUDA, Conda, and Python pre-installed.

In your workflows, you can create custom Conda environments via `conda env create`, 
save them as artifact (via [`artifacts`](examples/index.md#artifacts)), 
and reuse later from other workflows (via [`deps`](examples/index.md#deps) and [`conda activate`](examples/index.md#conda-environments)).

### Managing data

If your workflow produces data, you save it as an artifact (via [`artifacts`](examples/index#artifacts))
and reuse later from other workflows (via [`deps`](examples/index.md#deps)).

### Dev environments

You can quickly create a dev environment (such as VS Code or JupyterLab) with required
resources (such as GPU or memory) using the [code](reference/providers/index.md#code), 
[lab](reference/providers/index.md#lab), or [notebook](reference/providers/index.md#notebook) providers.

`dstack` will automatically create a machine in your cloud account with required resources and provide you a link to
open the dev environment. 
The dev environment will have your Git repo checked out and the required environment (Conda, CUDA, etc) configured.