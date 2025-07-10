<div style="text-align: center;">
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
[![Discord](https://img.shields.io/discord/1106906313969123368?style=flat-square)](https://discord.gg/u8SmfwPpMd)

</div>

`dstack` is an open-source container orchestrator that simplifies workload orchestration and drives GPU utilization for ML teams. It works with any GPU cloud, on-prem cluster, or accelerated hardware.

#### Accelerators

`dstack` supports `NVIDIA`, `AMD`, `Google TPU`, `Intel Gaudi`, and `Tenstorrent` accelerators out of the box.

## Latest news ✨
- [2025/07] [dstack 0.19.17: Secrets, Files, Rolling deployment](https://github.com/dstackai/dstack/releases/tag/0.19.17)
- [2025/06] [dstack 0.19.16: Docker in Docker, CloudRift](https://github.com/dstackai/dstack/releases/tag/0.19.16)
- [2025/06] [dstack 0.19.13: InfiniBand support in default images](https://github.com/dstackai/dstack/releases/tag/0.19.13)
- [2025/06] [dstack 0.19.12: Simplified use of MPI](https://github.com/dstackai/dstack/releases/tag/0.19.12)
- [2025/05] [dstack 0.19.10: Priorities](https://github.com/dstackai/dstack/releases/tag/0.19.10)
- [2025/05] [dstack 0.19.8: Nebius clusters, GH200 on Lambda](https://github.com/dstackai/dstack/releases/tag/0.19.8)
- [2025/04] [dstack 0.19.6: Tenstorrent, Plugins](https://github.com/dstackai/dstack/releases/tag/0.19.6)

## How does it work?

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://dstack.ai/static-assets/static-assets/images/dstack-architecture-diagram-v10-dark.svg"/>
  <img src="https://dstack.ai/static-assets/static-assets/images/dstack-architecture-diagram-v10.svg" width="750" />
</picture>

### Installation

> Before using `dstack` through CLI or API, set up a `dstack` server. If you already have a running `dstack` server, you only need to [set up the CLI](#set-up-the-cli).

#### Set up the server

##### (Optional) Configure backends

To use `dstack` with cloud providers, configure backends
via the `~/.dstack/server/config.yml` file.

For more details on how to configure backends, check [Backends](https://dstack.ai/docs/concepts/backends).

> For using `dstack` with on-prem servers, create [SSH fleets](https://dstack.ai/docs/concepts/fleets#ssh) 
> once the server is up.

##### Start the server

You can install the server on Linux, macOS, and Windows (via WSL 2). It requires Git and
OpenSSH.

##### uv

```shell
$ uv tool install "dstack[all]" -U
```

##### pip

```shell
$ pip install "dstack[all]" -U
```

Once it's installed, go ahead and start the server.

```shell
$ dstack server
Applying ~/.dstack/server/config.yml...

The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
The server is running at http://127.0.0.1:3000/
```

> For more details on server configuration options, see the
[Server deployment](https://dstack.ai/docs/guides/server-deployment) guide.


<details><summary>Set up the CLI</summary>

#### Set up the CLI

Once the server is up, you can access it via the `dstack` CLI. 

The CLI can be installed on Linux, macOS, and Windows. It requires Git and OpenSSH.

##### uv

```shell
$ uv tool install dstack -U
```

##### pip

```shell
$ pip install dstack -U
```

To point the CLI to the `dstack` server, configure it
with the server address, user token, and project name:

```shell
$ dstack project add \
    --name main \
    --url http://127.0.0.1:3000 \
    --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
    
Configuration is updated at ~/.dstack/config.yml
```

</details>

### Define configurations

`dstack` supports the following configurations:
   
* [Dev environments](https://dstack.ai/docs/dev-environments) &mdash; for interactive development using a desktop IDE
* [Tasks](https://dstack.ai/docs/tasks) &mdash; for scheduling jobs (incl. distributed jobs) or running web apps
* [Services](https://dstack.ai/docs/services) &mdash; for deployment of models and web apps (with auto-scaling and authorization)
* [Fleets](https://dstack.ai/docs/fleets) &mdash; for managing cloud and on-prem clusters
* [Volumes](https://dstack.ai/docs/concepts/volumes) &mdash; for managing persisted volumes
* [Gateways](https://dstack.ai/docs/concepts/gateways) &mdash; for configuring the ingress traffic and public endpoints

Configuration can be defined as YAML files within your repo.

### Apply configurations

Apply the configuration either via the `dstack apply` CLI command or through a programmatic API.

`dstack` automatically manages provisioning, job queuing, auto-scaling, networking, volumes, run failures,
out-of-capacity errors, port-forwarding, and more &mdash; across clouds and on-prem clusters.

## Useful links

For additional information, see the following links:

* [Docs](https://dstack.ai/docs)
* [Examples](https://dstack.ai/examples)
* [Discord](https://discord.gg/u8SmfwPpMd)

## Contributing

You're very welcome to contribute to `dstack`. 
Learn more about how to contribute to the project at [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Mozilla Public License 2.0](LICENSE.md)
