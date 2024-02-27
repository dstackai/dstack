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
Orchestrate GPU workloads effortlessly on any cloud
</h3>

<p align="center">
<a href="https://dstack.ai/docs" target="_blank"><b>Docs</b></a> •
<a href="https://dstack.ai/examples" target="_blank"><b>Examples</b></a> •
<a href="https://discord.gg/u8SmfwPpMd" target="_blank"><b>Discord</b></a>
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack?style=flat-square)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat-square&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
</div>

`dstack` is an open-source engine for running GPU workloads on any cloud.
It works with a wide range of cloud GPU providers (AWS, GCP, Azure, Lambda, TensorDock, Vast.ai, etc.)
as well as on-premises servers.

## Latest news ✨

- [2024/02] [dstack 0.16.0: Pools](https://dstack.ai/changelog/0.16.0/) (Release)
- [2024/02] [dstack 0.15.1: Kubernetes integration](https://dstack.ai/changelog/0.15.1/) (Release)
- [2024/01] [dstack 0.15.0: Resources, authentication, and more](https://dstack.ai/changelog/0.15.0/) (Release)
- [2024/01] [dstack 0.14.0: OpenAI-compatible endpoints](https://dstack.ai/changelog/0.14.0/) (Release)
- [2023/12] [dstack 0.13.0: Disk size, CUDA 12.1, Mixtral, and more](https://dstack.ai/changelog/0.13.0/) (Release)

## Installation

Before using `dstack` through CLI or API, set up a `dstack` server.

### Install the server
    
The easiest way to install the server, is via `pip`:

```shell
pip install "dstack[all]" -U
```

### Configure backends

If you have default AWS, GCP, or Azure credentials on your machine, the `dstack` server will pick them up automatically.

Otherwise, you need to manually specify the cloud credentials in `~/.dstack/server/config.yml`.

For further details on setting up the server, refer to [installation](https://dstack.ai/docs/installation/).

### Start the server

To start the server, use the `dstack server` command:

<div class="termy">

```shell
$ dstack server

Applying ~/.dstack/server/config.yml...

The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
The server is running at http://127.0.0.1:3000/
```

</div>

> **Note**
> It's also possible to run the server via [Docker](https://hub.docker.com/r/dstackai/dstack).

### CLI & API

Once the server is up, you can use either `dstack`'s CLI or API to run workloads.
Below is a live demo of how it works with the CLI.

### Dev environments

Dev environments allow you to quickly provision a machine with a pre-configured environment, resources, IDE, code, etc.

<img src="https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-dev-environment.gif" width="650"/>

### Tasks

Tasks are perfect for scheduling all kinds of jobs (e.g., training, fine-tuning, processing data, batch inference, etc.)
as well as running web applications.

<img src="https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-task.gif" width="650"/>

### Services

Services make it very easy to deploy any model or web application as a public endpoint.

<img src="https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-service-openai.gif" width="650"/>

## Examples

Here are some featured examples:

- [TGI](https://dstack.ai/examples/tgi/)
- [vLLM](https://dstack.ai/examples/vllm/)
- [Ollama](https://dstack.ai/examples/ollama/)
- [SDXL](https://dstack.ai/examples/sdxl/)
- [QLoRA](https://dstack.ai/examples/qlora/)

Browse [dstack.ai/examples](https://dstack.ai/examples) for more examples.

## More information

For additional information and examples, see the following links:

- [Docs](https://dstack.ai/docs)
- [Discord](https://discord.gg/u8SmfwPpMd)

## Licence

[Mozilla Public License 2.0](LICENSE.md)
