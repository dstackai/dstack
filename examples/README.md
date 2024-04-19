# Examples

This folder contains examples showing how to use `dstack`.

> [!NOTE]
> If you'd like to add your own example of using dstack or improve any of the existing ones, your PR is very welcome in this repository.

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