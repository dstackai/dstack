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
Run LLM workloads across any clouds
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

`dstack` is an open-source toolkit for running LLM workloads across any clouds, offering a
cost-efficient and user-friendly interface for training, inference, and development.

## Latest news ✨

- [2023/09] [Managed gateways for serving LLMs across clouds](https://dstack.ai/blog/2023/09/01/managed-gateways) (Release)
- [2023/08] [Fine-tuning with Llama 2](https://dstack.ai/examples/finetuning-llama-2) (Example)
- [2023/08] [Serving SDXL with FastAPI](https://dstack.ai/examples/stable-diffusion-xl) (Example)
- [2023/07] [Serving LLMS with TGI](https://dstack.ai/examples/text-generation-inference) (Example)
- [2023/07] [Serving LLMS with vLLM](https://dstack.ai/examples/vllm) (Example)

## Installation

To use `dstack`, install it with `pip`, and start the server.

```shell
pip install "dstack[aws,gcp,azure,lambda]"
dstack start
```
## Configure backends

Upon startup, the server sets up the default project called `main`. Prior to using `dstack`, you must log in to the
UI, open the project's settings, and configure cloud backends 
(e.g., [AWS](https://dstack.ai/docs/reference/backends/aws), [GCP](https://dstack.ai/docs/reference/backends/gcp), [Azure](https://dstack.ai/docs/reference/backends/azure), 
[Lambda](https://dstack.ai/docs/reference/backends/lambda), etc.).

## Define a configuration

A configuration is a YAML file that describes what you want to run.

> **Note**
> All configuration files must be named with the suffix `.dstack.yml`. For example,
> you can name the configuration file `.dstack.yml` or `app.dstack.yml`. You can define
> these configurations anywhere within your project.

Configurations can be of three types: `dev-environment`, `task`, and `service`.

### Dev environments

A dev environment is a virtual machine with a pre-configured IDE.

```yaml
type: dev-environment

python: "3.11" # (Optional) If not specified, your local version is used

setup: # (Optional) Executed once at the first startup
  - pip install -r requirements.txt

ide: vscode
```

### Tasks

A task can be either a batch job, such as training or fine-tuning a model, or a web application.

```yaml
type: task

python: "3.11" # (Optional) If not specified, your local version is used

ports:
  - 7860

commands:
  - pip install -r requirements.txt
  - python app.py
```

While the task runs in the cloud, the CLI forwards traffic, allowing you to access the application from your local
machine.

### Services

A service is an application that is accessible through a public endpoint.

```yaml
type: service

port: 7860

commands:
  - pip install -r requirements.txt
  - python app.py
```

Once the service is up, `dstack` makes it accessible from the Internet through
the [gateway](https://dstack.ai/docs/guides/services.md#configure-a-gateway-address).

## CLI

To run a configuration, use the [`dstack run`](https://dstack.ai/docs/reference/cli/run.md) command followed by 
working directory and the path to the configuration file.

```shell
dstack run . -f text-generation-inference/serve.dstack.yml --gpu A100 -y

 RUN           BACKEND  INSTANCE              SPOT  PRICE STATUS    SUBMITTED
 tasty-zebra-1 lambda   200GB, 1xA100 (80GB)  no    $1.1  Submitted now
 
Privisioning...

Serving on https://tasty-zebra-1.mydomain.com
```

`dstack` automatically provisions cloud resources based in the 
configured clouds that offer the best price and availability.

## More information

For additional information and examples, see the following links:

- [Docs](https://dstack.ai/docs)
- [Examples](https://dstack.ai/examples)
- [Blog](https://dstack.ai/blog)
- [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

## Licence

[Mozilla Public License 2.0](LICENSE.md)
