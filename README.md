<div style="text-align: center;">
<h2>
  <a target="_blank" href="https://dstack.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dstackai/dstack/master/mkdocs/assets/images/dstack-logo-dark.svg"/>
      <img alt="dstack" src="https://raw.githubusercontent.com/dstackai/dstack/master/mkdocs/assets/images/dstack-logo.svg" width="350px"/>
    </picture>
  </a>
</h2>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack?style=flat-square)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat-square&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
[![Discord](https://img.shields.io/discord/1106906313969123368?style=flat-square)](https://discord.gg/u8SmfwPpMd)

</div>

`dstack` is a unified control plane for GPU provisioning and orchestration that works with any GPU cloud, Kubernetes, or on-prem clusters. 

It streamlines development, training, and inference, and is compatible with any hardware, open-source tools, and frameworks.

#### Accelerators

`dstack` supports `NVIDIA`, `AMD`, `Google TPU`, and `Tenstorrent` accelerators out of the box.

## Latest news ✨
- [2026/08] [dstack 0.21.0: Pydantic v2, Gateway replicas](https://github.com/dstackai/dstack/releases/tag/0.21.0)
- [2026/07] [dstack 0.20.29: Presets — agent-driven inference optimization (experimental)](https://dstack.ai/docs/concepts/presets/)
- [2026/07] [dstack 0.20.27: Slurm backend](https://github.com/dstackai/dstack/releases/tag/0.20.27)
- [2026/05] [dstack 0.20.21: Kubernetes multiple clusters](https://github.com/dstackai/dstack/releases/tag/0.20.21)
- [2026/05] [dstack 0.20.20: NVIDIA Dynamo integration](https://github.com/dstackai/dstack/releases/tag/0.20.20)
- [2026/04] [dstack 0.20.17: Kubernetes volumes](https://github.com/dstackai/dstack/releases/tag/0.20.17)
- [2026/02] [dstack 0.20.10: PD disaggregation support](https://github.com/dstackai/dstack/releases/tag/0.20.10)
- [2026/01] [dstack 0.20.7: Replica groups](https://github.com/dstackai/dstack/releases/tag/0.20.7)

## How does it work?

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://dstack.ai/static-assets/static-assets/images/dstack-architecture-diagram-dark.svg"/>
  <img src="https://dstack.ai/static-assets/static-assets/images/dstack-architecture-diagram.svg" width="750" />
</picture>

### Launch the server

> Before using `dstack` through CLI or API, set up a `dstack` server. If you already have a running `dstack` server, you only need to [install the CLI](#install-the-cli).

To orchestrate compute across GPU clouds or Kubernetes clusters, you need to [configure backends](https://dstack.ai/docs/concepts/backends).

> When using `dstack` with on-prem servers, backend configuration isn’t required. Simply create [SSH fleets](https://dstack.ai/docs/concepts/fleets#ssh-fleets) once the server is up.

The server can be installed on Linux, macOS, and Windows (via WSL 2). It requires Git and
OpenSSH.

```shell
$ uv tool install "dstack[all]" -U
$ dstack server

Applying ~/.dstack/server/config.yml...

The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
The server is running at http://127.0.0.1:3000/
```

> For more details on server configuration options, see the
[Server deployment](https://dstack.ai/docs/guides/server-deployment) guide.

### Install the CLI

<details><summary>If the CLI is not installed with the server</summary>

Once the server is up, you can access it via the `dstack` CLI.

The CLI can be installed on Linux, macOS, and Windows. It requires Git and OpenSSH.

```shell
$ uv tool install dstack -U
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

### Install agent skills

Install [`dstack` skills](https://skills.sh/dstackai/dstack/dstack) to help AI agents use the CLI and edit configuration files.

```shell
$ npx skills add dstackai/dstack
```

AI agents like Claude, Codex, and Cursor can now create and manage fleets and submit workloads on your behalf.

### Define configurations

`dstack` supports the following configurations:
   
* [Fleets](https://dstack.ai/docs/concepts/fleets) &mdash; Provision and manage clusters across clouds, Kubernetes, and on-prem
* [Dev environments](https://dstack.ai/docs/concepts/dev-environments) &mdash; Launch dev environments to be accessed by agents or from your IDE
* [Tasks](https://dstack.ai/docs/concepts/tasks) &mdash; Run training, batch or other jobs across a single node or clusters
* [Services](https://dstack.ai/docs/concepts/services) &mdash; Deploy model inference as secure and scalable endpoints
* [Presets](https://dstack.ai/docs/concepts/presets) &mdash; Agent-driven inference optimization (experimental)
* [Volumes](https://dstack.ai/docs/concepts/volumes) &mdash; Managing instance and network volumes for persisting data

Configuration can be defined as YAML files within your repo.

### Apply configurations

Apply the configuration via the `dstack apply` CLI command, a programmatic API, or through [AI agent skills](#install-ai-agent-skills).

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
