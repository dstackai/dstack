<div>
<h2>
  <a target="_blank" href="https://dstack.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/images/dstack-logo-dark.svg"/>
      <img alt="dstack" src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/images/dstack-logo.svg" width="350px"/>
    </picture>
  </a>
</h2>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack?style=flat-square)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat-square&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
[![Discord](https://dcbadge.vercel.app/api/server/u8SmfwPpMd?style=flat-square)](https://discord.gg/CBgdrGnZjy)

</div>

`dstack` is an open-source container orchestration engine designed for running AI workloads across any cloud or data
center. It simplifies dev environments, running tasks on clusters, and deployment.

The supported cloud providers include AWS, GCP, Azure, OCI, Lambda, TensorDock, Vast.ai, RunPod, and CUDO.
You can also use `dstack` to run workloads on on-prem clusters.

`dstack` natively supports NVIDIA GPU, and Google Cloud TPU accelerator chips.
 
## Latest news ✨

- [2024/05] [dstack 0.18.3: OCI, and more](https://github.com/dstackai/dstack/releases/tag/0.18.3) (Release)
- [2024/05] [dstack 0.18.2: On-prem clusters, private subnets, and more](https://github.com/dstackai/dstack/releases/tag/0.18.2) (Release)
- [2024/04] [dstack 0.18.0: RunPod, multi-node tasks, and more](https://github.com/dstackai/dstack/releases/tag/0.18.0) (Release)
- [2024/03] [dstack 0.17.0: Auto-scaling, and other improvements](https://github.com/dstackai/dstack/releases/tag/0.17.0) (Release)

## Installation

Before using `dstack` through CLI or API, set up a `dstack` server.

### Install the server
    
The easiest way to install the server, is via `pip`:

```shell
pip install "dstack[all]" -U
```

### Configure backends

If you have default AWS, GCP, Azure, or OCI credentials on your machine, the `dstack` server will pick them up automatically.

Otherwise, you need to manually specify the cloud credentials in `~/.dstack/server/config.yml`.

See the [server/config.yml reference](https://dstack.ai/docs/reference/server/config.yml.md#examples)
for details on how to configure backends for all supported cloud providers.

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

You specify the required environment and resources, then run it. `dstack` provisions the dev
environment in the cloud and enables access via your desktop IDE.

<img src="https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-dev-environment.gif" width="650"/>

### Tasks

Tasks allow for convenient scheduling of any kind of batch jobs, such as training, fine-tuning,
or data processing, as well as running web applications.

Specify the environment and resources, then run it. `dstack` executes the task in the
cloud, enabling port forwarding to your local machine for convenient access.

<img src="https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-task.gif" width="650"/>

### Services

Services make it very easy to deploy any kind of model or web application as public endpoints.

Use any serving frameworks and specify required resources. `dstack` deploys it in the configured
backend, handles authorization, and provides an OpenAI-compatible interface if needed.

<img src="https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-service-openai.gif" width="650"/>

### Pools

Pools simplify managing the lifecycle of cloud instances and enable their efficient reuse across runs.

You can have instances provisioned in the cloud automatically, or add them manually, configuring the required resources,
idle duration, etc.

<img src="https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-pool.gif" width="650"/>

## Examples

Here are some featured examples:

- [Llama 3](examples/llms/llama3)
- [Alignment Handbook](examples/fine-tuning/alignment-handbook)
- [vLLM](examples/deployment/vllm)
- [Axolotl](examples/fine-tuning/axolotl)
- [TGI](examples/deployment/tgi)
- [Ollama](examples/deployment/ollama)
- [LoRaX](examples/deployment/lorax)

Browse [examples](examples) for more examples.

## More information

For additional information and examples, see the following links:

- [Docs](https://dstack.ai/docs)
- [Discord](https://discord.gg/u8SmfwPpMd)

## Contributing

We welcome contributions to `dstack`!
To learn more about getting involved in the project, please refer to [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Mozilla Public License 2.0](LICENSE.md)
