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
Effortlessly train and deploy generative AI
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

`dstack` is an open-source platform for training, fine-tuning, and deployment of 
generative AI models across various cloud providers (e.g., AWS, GCP, Azure, Lambda Cloud, etc.)

## Latest news ✨

- [2023/10] [Fine-tuning API](https://dstack.ai/docs/guides/fine-tuning/) (Release)
- [2023/10] [Simplified cloud setup, and refined API](https://dstack.ai/blog/2023/10/18/simplified-cloud-setup/) (Release)
- [2023/09] [RAG with Llama Index and Weaviate](https://dstack.ai/examples/llama-index-weaviate) (Example)
- [2023/09] [Deploying LLMs using Python API](https://dstack.ai/examples/deploy-python) (Example)
- [2023/08] [Fine-tuning Llama 2 using QLoRA](https://dstack.ai/examples/finetuning-llama-2) (Example)
- [2023/08] [Deploying Stable Diffusion using FastAPI](https://dstack.ai/examples/stable-diffusion-xl) (Example)
- [2023/07] [Deploying LLMS using TGI](https://dstack.ai/examples/text-generation-inference) (Example)
- [2023/07] [Deploying LLMS using vLLM](https://dstack.ai/examples/vllm) (Example)

## Installation

Before using `dstack` through CLI or API, set up a `dstack` server.

### Install the server

The easiest way to install the server, is via `pip`:

<div class="termy">

```shell
$ pip install "dstack[all]" -U
```

</div>

### Configure clouds

If you have default AWS, GCP, or Azure credentials on your machine, `dstack` will pick them up automatically.

Otherwise, you need to manually specify the cloud credentials in `~/.dstack/server/config.yml`.
For further cloud configuration details, refer to [server configuration](https://dstack.ai/docs/configuration/server).

### Start the server

To start the server, use the `dstack server` command:

<div class="termy">

```shell
$ dstack server

The server is running at http://127.0.0.1:3000/.
The admin token is xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

</div>

## Using CLI

### Define a configuration

The CLI allows you to define what you want to run as a YAML file and
run it via the `dstack run` CLI command.

#### Dev environments

A dev environment is a cloud instance pre-configured with an IDE.

```yaml
type: dev-environment

python: "3.11" # (Optional) If not specified, your local version is used

ide: vscode
```

#### Tasks

A task can be a batch job or a web app.

```yaml
type: task

python: "3.11" # (Optional) If not specified, your local version is used

ports:
  - 6006

commands:
  - pip install -r requirements.txt
  - tensorboard --logdir ./logs &
  - python train.py
```

If you run a task, `dstack` forwards the configured ports to `localhost`.

#### Services

A service is a web app accessible from the Internet.

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest

env: 
  - MODEL_ID=TheBloke/Llama-2-13B-chat-GPTQ 

port: 80

commands:
  - text-generation-launcher --trust-remote-code --quantize gptq
```

> **Note:**
> Before you can run a service, you have to set up a [gateway](https://dstack.ai/docs/guides/services.md#set-up-a-gateway).

Running a service will make it available at `https://<run-name>.<your-domain>` using the
domain configured for the gateway.

### Run a configuration

To run a configuration, use the [`dstack run`](https://dstack.ai/docs/reference/cli/run.md) command followed by 
working directory and the path to the configuration file.

```shell
dstack run . -f text-generation-inference/serve.dstack.yml --gpu 80GB -y

 RUN           BACKEND  INSTANCE              SPOT  PRICE STATUS    SUBMITTED
 tasty-zebra-1 lambda   200GB, 1xA100 (80GB)  no    $1.1  Submitted now
 
Privisioning...

Serving on https://tasty-zebra-1.mydomain.com
```

## Using API

As an alternative to the CLI, you can run tasks and services and manage runs programmatically.

### Create a client

First, create an instance of `dstack.api.Client`:

```python
from dstack.api import Client, ClientError

try:
    client = Client.from_config()
except ClientError:
    print("Can't connect to the server")
```

### Submit a run

Here's an example of how to run a task:

```python
from dstack.api import Task, Resources, GPU

task = Task(
    image="ghcr.io/huggingface/text-generation-inference:latest",
    env={"MODEL_ID": "TheBloke/Llama-2-13B-chat-GPTQ"},
    commands=[
        "text-generation-launcher --trust-remote-code --quantize gptq",
    ],
    ports=["80"],
)

run = client.runs.submit(
    run_name="my-awesome-run",
    configuration=task,
    resources=Resources(gpu=GPU(memory="24GB")),
)
```

[//]: # (TODO: Explain how to mount a repo)

To forward the configured ports to `localhost`, use the `attach` and `detach` methods on the run.

```python
try:
    run.attach()
    
    # ...
except KeyboardInterrupt:
    run.stop(abort=True)
finally:
    run.detach()
```

## More information

For additional information and examples, see the following links:

- [Docs](https://dstack.ai/docs)
- [Examples](https://dstack.ai/examples)
- [Blog](https://dstack.ai/blog)
- [Discord](https://discord.gg/u8SmfwPpMd)

## Licence

[Mozilla Public License 2.0](LICENSE.md)
