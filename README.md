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

 * Define workflows, incl. dependencies, environment, and required compute resources, via declarative configuration files.
 * Run workflows in the cloud via the `dstack` CLI.
 * Save output artifacts of workflows and reuse them in other workflows.
 * Use workflows to process data, train models, host apps, and launch dev environments.

## Installation

Use pip to install the `dstack` CLI:

```shell
pip install dstack
```

When you run workflows via the `dstack` CLI, dstack provisions compute resources
and saves data in your AWS account.

The `dstack` CLI needs your AWS account credentials to be configured locally 
(e.g. in `~/.aws/credentials` or `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables).

```shell
dstack config
```

This command will help you configure the AWS region, where dstack will provision compute resources, and
the S3 bucket, where dstack will save data.

```shell
Region name (eu-west-1):
S3 bucket name (dstack-142421590066-eu-west-1):
```

## How does it work?

 * Install `dstack` CLI locally
 * Define workflows in `.dstack/workflows.yaml` within your project directory
 * Use the `dstack` CLI to run workflows, manage their state and artifacts 
 * When you run a workflow, the `dstack` CLI  provisions the required cloud resources, 
   fetches your code, prepares environment, downloads dependencies, runs the workflow,
   saves artifacts, and tears down cloud resources.

## More information

 * [Documentation](https://docs.dstack.ai)
 * [Issue tracker](https://github.com/dstackai/dstack/issues)
 * [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
 * [Newsletter](https://dstack.curated.co/)
 * [Twitter](https://twitter.com/dstackai)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)