# Serving LLMs with TGI

Serving LLMs can be slow, even on expensive hardware. This example demonstrates how to utilize
[Text Generation Inference](https://github.com/huggingface/text-generation-inference) (TGI) to serve LLMs with
optimized performance. 

## What is TGI?

TGI is an open-source tool by Hugging Face that increases LLM throughput, thanks to the optimized memory-sharing
algorithms such as FlashAttention and PageAttention.

The tool also provides other benefits such as continuous batching, 
GPU parallelism, streaming output, quantization, water-marking, and more.

To try TGI with `dstack`, follow the instructions below.

## Prerequisites

!!! info "NOTE:"
    Before using `dstack` with a particular cloud, make sure to [configure](../docs/guides/projects.md) the corresponding project.

Each LLM model requires specific resources. To inform `dstack` about the required resources, you need to 
[define](../docs/reference/profiles.yml.md) a profile via the `.dstack/profiles.yaml` file within your project.

Below is a profile that will provision a cloud instance with `24GB` of memory and a `T4` GPU in the `gcp` project.

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: gcp-t4
    project: gcp
    resources:
      memory: 24GB
      gpu:
        name: T4
    default: true
```

</div>

## Running an endpoint

Here's the configuration that runs an LLM as an endpoint:

<div editor-title="text-generation-inference/serve.dstack.yml"> 

```yaml
type: task

image: ghcr.io/huggingface/text-generation-inference:0.9.3

env:
  # (Required) Specify the name of the model
  - MODEL_ID=tiiuae/falcon-7b
  # (Optional) Specify your Hugging Face token
  - HUGGING_FACE_HUB_TOKEN=

ports:
 - 8000

commands: 
  - text-generation-launcher --hostname 0.0.0.0 --port 8000 --trust-remote-code
```

</div>

Here's how you run it with `dstack`:

<div class="termy">

```shell
$ dstack run . -f text-generation-inference/serve.dstack.yml --ports 8000:8000
```

</div>

`dstack` will provision the cloud instance, run the task, and forward the defined ports to your local
machine for secure and convenient access.

Now, you can query the endpoint:

<div class="termy">

```shell
$ curl -X POST --location http://127.0.0.1:8000/generate \
    -H 'Content-Type: application/json' \
    -d '{
          "inputs": "What is Deep Learning?",
          "parameters": {
            "max_new_tokens": 20
          }
        }'
```

</div>

For more details on how `text-generation-inference` works, check 
their [repo](https://github.com/huggingface/text-generation-inference).

## Running a dev environment

Dev environments require the Docker image to have `openssh-server` pre-installed. 
While `dstack`'s default Docker images include it, the `ghcr.io/huggingface/text-generation-inference` Docker 
image lacks it. Therefore, ensure that you manually install `openssh-server` using the `build` property.

<div editor-title="text-generation-inference/.dstack.yml">

```yaml
type: dev-environment

image: ghcr.io/huggingface/text-generation-inference:0.9.3

build:
  - apt-get update
  - DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server
  - rm -rf /var/lib/apt/lists/*

ide: vscode
```

</div>

!!! info "Limitations"
    Since version 1.0.0, TGI has [changed](https://github.com/huggingface/text-generation-inference/issues/726) 
    the license and restricted the use of TGI for commercial purposes. 

[Source code](https://github.com/dstackai/dstack-examples){ .md-button .md-button--github }
