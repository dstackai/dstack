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

`dstack` is a lightweight alternative to Kubernetes built for AI. It simplifies container orchestration for AI across
in the cloud and on-prem, accelerating the development, training, and deployment of AI models at any scale.

`dstack` supports [on-prem](https://dstack.ai/docs/concepts/fleets#on-prem) servers and natively integrates with a variety of [providers](https://dstack.ai/providers). 

#### Accelerators

`dstack` supports `NVIDIA GPU`, `AMD GPU`, and `Google Cloud TPU` out of the box.

## Major news ✨

- [2024/08] [dstack 0.18.11: AMD, encryption, and more](https://github.com/dstackai/dstack/releases/tag/0.18.11) (Release)
- [2024/08] [dstack 0.18.10: Control plane UI](https://github.com/dstackai/dstack/releases/tag/0.18.10) (Release)
- [2024/07] [dstack 0.18.7: Fleets, RunPod volumes, dstack apply, and more](https://github.com/dstackai/dstack/releases/tag/0.18.7) (Release)
- [2024/05] [dstack 0.18.4: Google Cloud TPU, and more](https://github.com/dstackai/dstack/releases/tag/0.18.4) (Release)
- [2024/05] [dstack 0.18.2: On-prem clusters, private subnets, and more](https://github.com/dstackai/dstack/releases/tag/0.18.2) (Release)

## Installation

Before using `dstack` through CLI or API, set up a `dstack` server.

### 1. Configure backends

If you want the `dstack` server to run containers or manage clusters in your cloud accounts (or use Kubernetes),
create the [`~/.dstack/server/config.yml`](https://dstack.ai/docs/reference/server/config.yml) file and configure backends.

### 2. Start the server

Once backends are configured, proceed to start the server:

<div class="termy">

```shell
$ pip install "dstack[all]" -U
$ dstack server

Applying ~/.dstack/server/config.yml...

The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
The server is running at http://127.0.0.1:3000/
```

</div>

> **Note**
> It's also possible to run the server via [Docker](https://hub.docker.com/r/dstackai/dstack).

The `dstack` server can run anywhere: on your laptop, a dedicated server, or in the cloud. Once it's up, you
can use either the CLI or the API.

### 3. Set up the CLI

To point the CLI to the `dstack` server, configure it
with the server address, user token, and project name:

```shell
$ pip install dstack
$ dstack config --url http://127.0.0.1:3000 \
    --project main \
    --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
    
Configuration is updated at ~/.dstack/config.yml
```

### 4. Create on-prem fleets
    
> If you want the `dstack` server to run containers on your on-prem servers,
use [fleets](https://dstack.ai/docs/concepts/fleets).

## How does it work?

> Before using `dstack`, [install](https://dstack.ai/docs/installation) the server and configure backends.

### 1. Define configurations

`dstack` supports the following configurations:
   
* [Dev environments](https://dstack.ai/docs/dev-environments) &mdash; for interactive development using a desktop IDE
* [Tasks](https://dstack.ai/docs/tasks) &mdash; for scheduling jobs (incl. distributed jobs) or running web apps
* [Services](https://dstack.ai/docs/services) &mdash; for deployment of models and web apps (with auto-scaling and authorization)
* [Fleets](https://dstack.ai/docs/fleets) &mdash; for managing cloud and on-prem clusters
* [Volumes](https://dstack.ai/docs/concepts/volumes) &mdash; for managing persisted volumes
* [Gateways](https://dstack.ai/docs/concepts/gateways) &mdash; for configuring the ingress traffic and public endpoints

Configuration can be defined as YAML files within your repo.

### 2. Apply configurations

Apply the configuration either via the `dstack apply` CLI command or through a programmatic API.

`dstack` automatically manages provisioning, job queuing, auto-scaling, networking, volumes, run failures,
out-of-capacity errors, port-forwarding, and more &mdash; across clouds and on-prem clusters.

## More information

For additional information and examples, see the following links:

* [Docs](https://dstack.ai/docs)
* [Examples](https://dstack.ai/examples)
* [Providers](https://dstack.ai/providers)
* [Discord](https://discord.gg/u8SmfwPpMd)

## Contributing

You're very welcome to contribute to `dstack`. 
Learn more about how to contribute to the project at [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Mozilla Public License 2.0](LICENSE.md)
