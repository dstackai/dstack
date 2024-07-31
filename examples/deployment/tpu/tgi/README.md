# Deploy TGI on Cloud TPU instance

This example shows how to deploy the `Mistral-7B` model on TPU [v5e](https://cloud.google.com/tpu/docs/v5e) as an endpoint using [🤗Hugging Face Optimum TPU](https://github.com/huggingface/optimum-tpu) with `dstack`. 

## Optimum-TPU

The Optimum-TPU framework simplifies TPU deployment by providing an interface similar to the Hugging Face transformers library. It includes [Text Generation Inference (TGI)](https://github.com/huggingface/optimum-tpu/tree/main/text-generation-inference) backend 
allowing to deploy and serve incoming HTTP requests and execute them on Cloud TPUs.
It utilizes all TPU Cores during inference, ensuring maximum performance and efficient resource utilization.

Currently, Optimum-TPU supports the following LLM models for inference:

- Gemma (2b, 7b)
- Llama2 (7b) and Llama3 (8b)
- Mistral (7b)

## Prerequisites

Before following this tutorial, ensure you've [installed](https://dstack.ai/docs/installation) `dstack`.

## Deploy as `dstack` Task
The easiest way to run Inference is by creating a `dstack` task configuration file. This file can be found at [serve-task.dstack.yml](serve-task.dstack.yml). Below is its content:

```yaml
type: task
# This task runs Mistral-7B with TGI

image: huggingface/optimum-tpu:latest
env:
  - HUGGING_FACE_HUB_TOKEN
  - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.2
commands:
  - text-generation-launcher --port 8000 --max-concurrent-requests 4 --max-input-tokens 128 --max-total-tokens 150 --max-batch-prefill-tokens 128
ports:
  - 8000

resources:
  gpu: tpu-v5litepod-8
```
The task runs a container with optimum-tpu image and then launches `Mistral-7B-Instruct-v0.2` at port `8000`.

To, run the task use `dstack run`

```shell
dstack run . -f examples/deployment/tpu/tgi/serve-task.dstack.yml
```
See the configuration at [serve-task.dstack.yml](serve-task.dstack.yml).

For more details about Tasks, refer to [tasks](https://dstack.ai/docs/concepts/tasks)

## Service

The following command deploys Mistral 7B Instruct as a service:

```shell
dstack run . -f examples/deployment/tpu/tgi/serve.dstack.yml
```
See the configuration at [serve.dstack.yml](serve.dstack.yml).

For more details about Services, refer to [services](https://dstack.ai/docs/concepts/services).

## Text Generation Launcher Arguments

```shell
--max-concurrent-requests #concurrent clients requests 
--max-input-tokens # maximum allowed input length
--max-total-tokens # should be equal to max-input-token + max_new_tokens
--max-batch-prefill-tokens # limits the number of tokens for the prefill operation and should be equal to --max-input-tokens
```

See [CLI reference](https://huggingface.co/docs/text-generation-inference/en/basic_tutorials/launcher) for more details.