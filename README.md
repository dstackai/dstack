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
Orchestrate GPU workloads across clouds
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

`dstack` is an open-source framework for orchestrating GPU workloads
across multiple cloud GPU providers. It provides a simple cloud-agnostic interface for 
development and deployment of generative AI models.

## Latest news ✨

- [2023/09] [Deploying LLMs using Python API](https://dstack.ai/examples/python-api) (Example)
- [2023/09] [Managed gateways](https://dstack.ai/blog/2023/09/01/managed-gateways) (Release)
- [2023/08] [Fine-tuning Llama 2 using QLoRA](https://dstack.ai/examples/finetuning-llama-2) (Example)
- [2023/08] [Deploying Stable Diffusion using FastAPI](https://dstack.ai/examples/stable-diffusion-xl) (Example)
- [2023/07] [Deploying LLMS using TGI](https://dstack.ai/examples/text-generation-inference) (Example)
- [2023/07] [Deploying LLMS using vLLM](https://dstack.ai/examples/vllm) (Example)

## Installation

To use `dstack`, install it with `pip`, and start the server.

```shell
pip install "dstack[all]" -U
dstack start
```
## Configure clouds

Upon startup, the server sets up the default project called `main`.
Prior to using `dstack`, make sure to [configure clouds](https://dstack.ai/docs/guides/clouds#configure-backends).

Once the server is up, you can orchestrate GPU workloads using
either the CLI or Python API.

## Using CLI

### Define a configuration

The CLI allows you to define what you want to run as a YAML file and
run it via the `dstack run` CLI command.

Configurations can be of three types: `dev-environment`, `task`, and `service`.

#### Dev environments

A dev environment is a virtual machine with a pre-configured IDE.

```yaml
type: dev-environment

python: "3.11" # (Optional) If not specified, your local version is used

setup: # (Optional) Executed once at the first startup
  - pip install -r requirements.txt

ide: vscode
```

#### Tasks

A task can be either a batch job, such as training or fine-tuning a model, or a web application.

```yaml
type: task

python: "3.11" # (Optional) If not specified, your local version is used

ports:
  - 7860

commands:
  - pip install -r requirements.txt
  - python app.py
```

While the task is running in the cloud, the CLI forwards its ports traffic to `localhost`
for convenient access.

#### Services

A service is an application that is accessible through a public endpoint.

```yaml
type: service

port: 7860

commands:
  - pip install -r requirements.txt
  - python app.py
```

Once the service is up, `dstack` makes it accessible from the Internet through
the [gateway](https://dstack.ai/docs/guides/clouds#configure-gateways).

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

As an alternative to the CLI, you can run tasks and services programmatically 
via [Python API](https://dstack.ai/docs/reference/api/python/).

```python
import sys

import dstack

task = dstack.Task(
    image="ghcr.io/huggingface/text-generation-inference:latest",
    env={"MODEL_ID": "TheBloke/Llama-2-13B-chat-GPTQ"},
    commands=[
        "text-generation-launcher --trust-remote-code --quantize gptq",
    ],
    ports=["8080:80"],
)
resources = dstack.Resources(gpu=dstack.GPU(memory="20GB"))

if __name__ == "__main__":
    print("Initializing the client...")
    client = dstack.Client.from_config(repo_dir="~/dstack-examples")

    print("Submitting the run...")
    run = client.runs.submit(configuration=task, resources=resources)

    print(f"Run {run.name}: " + run.status())

    print("Attaching to the run...")
    run.attach()

    # After the endpoint is up, http://127.0.0.1:8080/health will return 200 (OK).

    try:
        for log in run.logs():
            sys.stdout.buffer.write(log)
            sys.stdout.buffer.flush()

    except KeyboardInterrupt:
        print("Aborting the run...")
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
