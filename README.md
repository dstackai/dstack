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
Train and deploy generative AI on any cloud
</h3>

<p align="center">
<a href="https://dstack.ai/docs" target="_blank"><b>Docs</b></a> •
<a href="https://dstack.ai/examples" target="_blank"><b>Examples</b></a> •
<a href="https://dstack.ai/blog" target="_blank"><b>Blog</b></a> •
<a href="https://discord.gg/u8SmfwPpMd" target="_blank"><b>Discord</b></a>
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack?style=flat-square)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat-square&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
</div>

`dstack` simplifies training, fine-tuning, and deploying
generative AI models on any cloud. 

Supported providers: AWS, GCP, Azure, Lambda, TensorDock, and Vast.ai.

## Latest news ✨

- [2023/11] [Access the GPU marketplace with Vast.ai](https://dstack.ai/blog/2023/11/21/vastai/) (Release)
- [2023/10] [Use world's cheapest GPUs with TensorDock](https://dstack.ai/blog/2023/10/31/tensordock/) (Release)
- [2023/10] [A preview of fine-tuning API](https://dstack.ai/docs/guides/fine-tuning/) (Release)
- [2023/09] [RAG with Llama Index and Weaviate](https://dstack.ai/examples/llama-index-weaviate) (Example)
- [2023/08] [Deploying Stable Diffusion using FastAPI](https://dstack.ai/examples/stable-diffusion-xl) (Example)
- [2023/07] [Deploying LLMs using TGI](https://dstack.ai/examples/text-generation-inference) (Example)
- [2023/07] [Deploying LLMs using vLLM](https://dstack.ai/examples/vllm) (Example)

## Installation

Before using `dstack` through CLI or API, set up a `dstack` server.

### Install the server
    
The easiest way to install the server, is via `pip`:

<div class="termy">

```shell
$ pip install "dstack[all]" -U
```

</div>

> Another way to install the server is through [Docker](https://hub.docker.com/r/dstackai/dstack).

### Configure the server

If you have default AWS, GCP, or Azure credentials on your machine, the `dstack` server will pick them up automatically.

Otherwise, you need to manually specify the cloud credentials in `~/.dstack/server/config.yml`.
For further details, refer to [server configuration](https://dstack.ai/docs/configuration/server/).

### Start the server

To start the server, use the `dstack server` command:

<div class="termy">

```shell
$ dstack server

Applying configuration...
---> 100%

The server is running at http://127.0.0.1:3000/.
The admin token is bbae0f28-d3dd-4820-bf61-8f4bb40815da
```

</div>

## More information

For additional information and examples, see the following links:

- [Docs](https://dstack.ai/docs)
- [Examples](https://dstack.ai/examples)
- [Blog](https://dstack.ai/blog)
- [Discord](https://discord.gg/u8SmfwPpMd)

## Licence

[Mozilla Public License 2.0](LICENSE.md)
