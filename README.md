<div align="center">
<h1 align="center">
  <a target="_blank" href="https://dstack.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/images/dstack-logo-dark.svg"/>
      <img alt="dstack" src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/images/dstack-logo.svg" width="350px"/>
    </picture>
  </a>
</h1>

<h3 align="center">
Cost-effective LLM development
</h3>

<p align="center">
<a href="https://dstack.ai/docs" target="_blank"><b>Docs</b></a> •
<a href="https://dstack.ai/examples" target="_blank"><b>Examples</b></a> •
<a href="https://dstack.ai/blog" target="_blank"><b>Blog</b></a> •
<a href="https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ" target="_blank"><b>Slack</b></a>
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack?style=flat-square)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat-square&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
</div>

`dstack` is an open-source tool that streamlines LLM development and deployment across multiple clouds.

It helps reduce cloud costs, improve availability, and frees you from cloud vendor lock-in.

## Latest news

- [2023/08] [Fine-tuning with Llama 2](https://dstack.ai/examples/finetuning-llama-2) (Example)
- [2023/08] [An early preview of services](https://dstack.ai/blog/2023/08/07/services-preview) (Release)
- [2023/07] [Port mapping, max duration, and more](https://dstack.ai/blog/2023/07/25/port-mapping-max-duration-and-more) (Release)
- [2023/07] [Serving with vLLM](https://dstack.ai/examples/vllm) (Example)
- [2023/07] [LLM as Chatbot](https://dstack.ai/examples/llmchat) (Example)
- [2023/07] [Lambda Cloud GA and Docker support](https://dstack.ai/blog/2023/07/14/lambda-cloud-ga-and-docker-support/) (Release)  
- [2023/06] [New YAML format](https://dstack.ai/blog/2023/06/12/new-configuration-format-and-cli-experience/) (Release)

## Installation

To use `dstack`, install it with `pip`, and start the server.

```shell
pip install "dstack[aws,gcp,azure,lambda]"
dstack start
```

To run dev environments, tasks, and services in the cloud, log into the UI, and
configure create the [corresponding project](https://dstack.ai/docs/projects).

## Configurations

A configuration is a YAML file that describes what you want to run.

> **Note**
> All configuration files must be named with the suffix `.dstack.yml`. For example,
> you can name the configuration file `.dstack.yml` or `app.dstack.yml`. You can define
> these configurations anywhere within your project.

Configurations can be of three types: `dev-environment`, `task`, and `service`.

### Dev environments

A dev environment is a virtual machine with a pre-configured IDE.
Here's an example of such a configuration:

```yaml
type: dev-environment

init:
  - pip install -r requirements.txt

ide: vscode
```

### Tasks

A task can be either a batch job, such as training or fine-tuning a model, or a web application.
Here's an example of a task configuration.

```yaml
type: task

commands:
  - pip install -r requirements.txt
  - python train.py
```

### Services

A service is an application that is accessible through a public endpoint
managed by `dstack`.
Here's an example of service:

```yaml
type: service

gateway: ${{ secrets.GATEWAY_ADDRESS }}

port: 8000

commands:
  - python -m http.server 8000
```

## CLI

To run a configuration, use the [`dstack run`](https://dstack.ai/docs/reference/cli/run.md) command followed by 
working directory and the path to the configuration file.

```shell
dstack run . -f serve.dstack.yml
```

`dstack` automatically provisions cloud resources based on the settings
of the configured project.

## Profiles

The `.dstack/profiles.yml` file allows describing multiple profiles.
Each profile can specify the project to use and the resources required for the run.

```yaml
profiles:
  - name: gpu-large
    project: gcp
    resources:
       memory: 48GB
       gpu:
         memory: 24GB
    spot_policy: auto
    default: true
```

If you have configured the default profile, the `dstack run` command will use it automatically.
Otherwise, you can always pass the profile using `--profile` to `dstack run`.

## More information

For additional information and examples, see the following links:

- [Docs](https://dstack.ai/docs)
- [Examples](https://dstack.ai/examples)
- [Blog](https://dstack.ai/blog)
- [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

## Licence

[Mozilla Public License 2.0](LICENSE.md)
