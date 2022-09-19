<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="300px"/>    

A lightweight command-line tool to run reproducible ML workflows in the cloud
______________________________________________________________________


[![PyPI](https://img.shields.io/github/workflow/status/dstackai/dstack/Build?style=for-the-badge)](https://github.com/dstackai/dstack/actions/workflows/build.yml)
[![PyPI](https://img.shields.io/pypi/v/dstack?style=for-the-badge)](https://pypi.org/project/dstack/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=for-the-badge&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

[Documentation](https://docs.dstack.ai) | [Issues](https://github.com/dstackai/dstack/issues) | [Twitter](https://twitter.com/dstackai) | [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

</div>

`dstack` is a lightweight command-line tool for running reproducible ML workflows in the cloud.

## Features

 * Define workflows (incl. their dependencies, environment and hardware requirements) as code.
 * Run workflows in the cloud using the `dstack` CLI. dstack provisions infrastructure and environment for you in the cloud.
 * Save output artifacts of workflows and reuse them in other workflows.

## Installation

Use pip to install the `dstack` CLI:

```shell
pip install dstack
```

Make sure the AWS account credentials are configured locally 
(e.g. in `~/.aws/credentials` or `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables.)

Before you can use the `dstack` CLI, you need to configure the AWS region where dstack will provision 
infrastructure and the S3 bucket where it will save data.

To do that, use the `dstack config` command.

```shell
dstack config
```

It will prompt you to enter an AWS profile name, a region name, and an S3 bucket name.

```shell
AWS profile name (default):
S3 bucket name:
Region name:
```

## How does it work?

 * You define workflows in `.dstack/workflows.yaml` within your project: environment and hardware requirements, dependencies, artifacts, etc.
 * You use the `dstack run` CLI command to run workflows
 * When you run a workflow, the CLI provisions infrastructure, prepares environment, fetches your code,
   downloads dependencies, runs the workflow, saves artifacts, and tears down infrastructure.
 * You assign tags to finished run, e.g. to reuse their output artifacts in other workflows.
 * Use workflows to process data, train models, host apps, and launch dev environments.

## More information

 * [Documentation](https://docs.dstack.ai)
 * [Issue tracker](https://github.com/dstackai/dstack/issues)
 * [Slack chat](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
 * [Twitter](https://twitter.com/dstackai)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)