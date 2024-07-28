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

`dstack` is an open-source container orchestration engine for AI. 
It accelerates the development, training, and deployment of AI models, and simplifies the management of clusters.

#### Cloud and on-prem

`dstack` is easy to use with any cloud or on-prem servers.
Supported cloud providers include AWS, GCP, Azure, OCI, Lambda, TensorDock, Vast.ai, RunPod, and CUDO.
For using `dstack` with on-prem servers, see [fleets](fleets.md#__tabbed_1_2).

#### Accelerators

`dstack` supports `NVIDIA GPU` and `Google Cloud TPU` out of the box.
 
## Major news ✨

- [2024/07] [dstack 0.18.7rc1: Fleets](https://github.com/dstackai/dstack/releases/tag/0.18.7) (Release)
- [2024/05] [dstack 0.18.4: Google Cloud TPU, and more](https://github.com/dstackai/dstack/releases/tag/0.18.4) (Release)
- [2024/05] [dstack 0.18.3: OCI, and more](https://github.com/dstackai/dstack/releases/tag/0.18.3) (Release)
- [2024/05] [dstack 0.18.2: On-prem clusters, private subnets, and more](https://github.com/dstackai/dstack/releases/tag/0.18.2) (Release)
- [2024/04] [dstack 0.18.0: RunPod, multi-node tasks, and more](https://github.com/dstackai/dstack/releases/tag/0.18.0) (Release)

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

### Add on-prem servers
    
> If you'd like to use `dstack` to run workloads on your on-prem servers,
see [on-prem fleets](https://dstack.ai/docs/fleets#__tabbed_1_2) command.

## How does it work?

### 1. Define run configurations

`dstack` supports three types of run configurations:
   
* [Dev environments](https://dstack.ai/docs/dev-environments.md) &mdash; for interactive development using a desktop IDE
* [Tasks](https://dstack.ai/docs/tasks.md) &mdash; for any kind of batch jobs or web applications (supports distributed jobs)
* [Services](https://dstack.ai/docs/services.md)&mdash; for production-grade deployment (supports auto-scaling and authorization)

Each type of run configuration allows you to specify commands for execution, required compute resources, retry policies, auto-scaling rules, authorization settings, and more.

Configuration can be defined as YAML files within your repo.

### 2. Run configurations

Run any defined configuration either via `dstack` CLI or API.
   
`dstack` automatically handles provisioning, interruptions, port-forwarding, auto-scaling, network, volumes, 
run failures, out-of-capacity errors, and more.

### 3. Manage fleets

Use [fleets](https://dstack.ai/docs/fleets.md) to provision and manage clusters and instances, both in the cloud and on-prem.

## More information

For additional information and examples, see the following links:

* [Docs](https://dstack.ai/docs)
* [Examples](examples)
* [Changelog](https://github.com/dstackai/dstack/releases)
* [Discord](https://discord.gg/u8SmfwPpMd)

## Contributing

You're very welcome to contribute to `dstack`. 
Learn more about how to contribute to the project at [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Mozilla Public License 2.0](LICENSE.md)
