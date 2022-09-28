<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="300px"/>    

A command-line utility to provision infrastructure for ML workflows
______________________________________________________________________


[![PyPI](https://img.shields.io/github/workflow/status/dstackai/dstack/Build?style=for-the-badge)](https://github.com/dstackai/dstack/actions/workflows/build.yml)
[![PyPI](https://img.shields.io/pypi/v/dstack?style=for-the-badge)](https://pypi.org/project/dstack/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=for-the-badge&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

[Documentation](https://docs.dstack.ai) | [Issues](https://github.com/dstackai/dstack/issues) | [Twitter](https://twitter.com/dstackai) | [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

</div>

`dstack` is a lightweight command-line utility to provision infrastructure for ML workflows.

[//]: # (An illustration courtesy of Storyset: https://storyset.com/people)
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/Ninja-amico.svg" width="450px"/>

## Highlights

 * Define your ML workflows declaratively, incl. their dependencies, environment, and required compute resources 
 * Run workflows via the `dstack` CLI. Have infrastructure provisioned automatically in a configured cloud account. 
 * Save output artifacts, such as data and models, and reuse them in other ML workflows
 * Use `dstack` to process data, train models, host apps, and launch dev environments

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

It will prompt you to select the AWS region 
where dstack will provision compute resources, and the S3 bucket, where dstack will save data.

```shell
Region name (eu-west-1):
S3 bucket name (dstack-142421590066-eu-west-1):
```

> Support for GCP and Azure is in the roadmap.

## How does it work?

1. Install `dstack` locally 
2. Define ML workflows in `.dstack/workflows.yaml` (within your existing Git repository)
3. Run ML workflows via the `dstack run` CLI command
4. Use other `dstack` CLI commands to manage runs, artifacts, etc.


>  When you run an ML workflow via the `dstack` CLI, it provisions the required compute resources (in a configured cloud
   account), sets up environment (such as Python, Conda, CUDA, etc), fetches your code, downloads deps,
   saves artifacts, and tears down compute resources.
 
## More information

 * [Documentation](https://docs.dstack.ai)
 * [Issue tracker](https://github.com/dstackai/dstack/issues)
 * [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
 * [Newsletter](https://dstack.curated.co/)
 * [Twitter](https://twitter.com/dstackai)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)