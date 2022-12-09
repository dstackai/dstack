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
Reproducible ML workflows for teams
</h4>

<p align="center">
<code>dstack</code> allows define ML workflows as code, and run them in a configured cloud via the CLI. 
It automatically handles workflow dependencies, provisions cloud infrastructure, and versions 
data, models, and environments.
</p>

[![Slack](https://img.shields.io/badge/slack-chat%20with%20us-blueviolet?logo=slack&style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

<p align="center">
<a href="https://docs.dstack.ai" target="_blank"><b>Docs</b></a> • 
<a href="https://docs.dstack.ai/examples" target="_blank"><b>Examples</b></a> • 
<a href="https://docs.dstack.ai/tutorials/quickstart"><b>Quickstart</b></a> • 
<a href="https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ" target="_blank"><b>Slack</b></a> 
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

</div>

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

## How does it work?

1. Install `dstack` CLI locally 
2. Configure the cloud credentials locally (e.g. via `~/.aws/credentials`)
3. Define ML workflows in `.dstack/workflows` (within your existing Git repository)
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

## More information

* [Docs](https://docs.dstack.ai/)
* [Examples](https://docs.dstack.ai/examples)
* [Innstallation](https://docs.dstack.ai/installation)
* [Quickstart](https://docs.dstack.ai/tutorials/quickstart)
* [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)