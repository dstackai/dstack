# Examples

This folder contains examples showing how to use `dstack`.

> [!IMPORTANT]
> Feel free to contribute your examples or enhance the existing ones—your PRs are warmly welcomed in this repo!

## Getting started

### Prerequisites

To use the open-source version, make sure to [install the server](https://dstack.ai/docs/installation/) and configure backends.

### Run examples

#### Init the repo

```shell
git clone https://github.com/dstackai/dstack
cd dstack
dstack init
```

#### Run a dev environment

Here's how to run a dev environment with the current repo:

```shell
dstack run . -f examples/.dstack.yml
```

#### Run other examples

Here's how to run other examples, e.g. [`deployment/vllm`](deployment/vllm/):

```shell
dstack run . -f examples/deployment/vllm/serve.dstack.yml
```

## Featrued

Here are some featured examples:

- [Llama 3](llms/llama3)
- [Alignment Handbook](fine-tuning/alignment-handbook)
- [vLLM](deployment/vllm)
- [Axolotl](fine-tuning/axolotl)
- [TGI](deployment/tgi)
- [Ollama](deployment/ollama)

Browse [deployment](deployment), [fine-tuning](deployment), [llms](llms), and [misc](misc) for more.

> [!IMPORTANT]
> Feel free to contribute your examples or enhance the existing ones—your PRs are warmly welcomed in this repo!