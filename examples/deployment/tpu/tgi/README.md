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

## Dev environment

If you'd like to play with the example using a dev environment, run
[.dstack.yml](.dstack.yml) via `dstack apply`:

```shell
dstack apply -f examples/deployment/tgi/.dstack.yaml 
```

## Deploy as `dstack` Task
The easiest way to deploy a model is by creating a `dstack` task configuration file. This file can be found at [serve-task.dstack.yml](serve-task.dstack.yml). Below is its content:

```yaml
type: task

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

To, run the task use `dstack apply` as below:

```shell
HUGGING_FACE_HUB_TOKEN=...

dstack apply -f examples/deployment/tpu/tgi/serve-task.dstack.yml
```

<details>
<summary>Example Output</summary>
Warming up the model can take 5+ minutes as indicated in the below output.

```shell
INFO text_generation_launcher: Starting Webserver
INFO text_generation_router: router/src/main.rs:195: Using the Hugging Face API
INFO hf_hub: /usr/local/cargo/registry/src/index.crates.io-6f17d22bba15001f/hf-hub-0.3.2/src/lib.rs:55: Token file not found "/root/.cache/huggingface/token"    
INFO text_generation_router: router/src/main.rs:474: Serving revision 83b95e8c912e57e3e941f1de69f4a7ee14a8ad92 of model mistralai/Mistral-7B-Instruct-v0.2
INFO text_generation_router: router/src/main.rs:289: Using config Some(Mistral)
INFO text_generation_router: router/src/main.rs:317: Warming up model
INFO text_generation_launcher: Warmup (this can take several minutes)
INFO text_generation_router: router/src/main.rs:354: Setting max batch total tokens to 150
INFO text_generation_router: router/src/main.rs:355: Connected
WARN text_generation_router: router/src/main.rs:369: Invalid hostname, defaulting to 0.0.0.0
```
</details>

You can now access the model as below:
```shell
dstack % curl localhost:8000/generate \
    -X POST \
    -d '{"inputs":"What is Deep Learning?","parameters":{"max_new_tokens":20}}' \
    -H 'Content-Type: application/json'
{"generated_text":"\n\nDeep Learning is a subset of Machine Learning, which is a subset of Artificial Intelligence."}
```
For more details about Tasks, refer to [tasks](https://dstack.ai/docs/concepts/tasks)

You can also adjust the TGI launcher arguments as below
```shell
--max-concurrent-requests #concurrent clients requests 
--max-input-tokens # maximum allowed input length
--max-total-tokens # should be equal to max-input-token + max_new_tokens
--max-batch-prefill-tokens # limits the number of tokens for the prefill operation and should be equal to --max-input-tokens
```
See [CLI reference](https://huggingface.co/docs/text-generation-inference/en/basic_tutorials/launcher) for more details.

## Deploy as `dstack` Service

With `dstack` service you can deploy models as a secure public endpoint. Before running your model as a service you need to set up `dstack` [gateway](https://dstack.ai/docs/concepts/gateways/).

Make sure the gateway is running as below:

Example Gateway
```shell 
dstack % dstack gateway list
BACKEND  REGION     NAME             HOSTNAME        DOMAIN        DEFAULT  STATUS  
aws      eu-west-1  example-gateway  18.206.244.126  example.com   ✓        running 
```

Then create a `dstack` service configuration file. This file can be found at [serve.dstack.yml](serve.dstack.yml). Below is its content.
```yaml
type: service

image: huggingface/optimum-tpu:latest
env:
  - HUGGING_FACE_HUB_TOKEN
  - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.2
commands:
  - text-generation-launcher --port 8000 --max-concurrent-requests 4 --max-input-tokens 128 --max-total-tokens 150 --max-batch-prefill-tokens 128
port: 8000

resources:
  gpu: tpu-v5litepod-8

# (Optional) Enable the OpenAI-compatible endpoint
model:
  format: tgi
  type: chat
  name: mistralai/Mistral-7B-Instruct-v0.2
```

To, run the service use `dstack apply` as below:

```shell
HUGGING_FACE_HUB_TOKEN=...

dstack apply -f examples/deployment/tpu/tgi/serve.dstack.yml
```
You can now access the model as below:

```shell
dstack % curl -X POST "https://example.com/generate" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer your_token" \
    -d '{"inputs":"What is deep learning?","parameters":{"max_new_tokens":30}}' 
{"generated_text":" Deep learning is a subset of machine learning, which is a type of artificial intelligence (AI) that uses neural networks with three or more layers to model"}                       
```
For more details about Services, refer to [services](https://dstack.ai/docs/concepts/services).

## Source code

The source-code of this example can be found in  [`https://github.com/dstackai/dstack/examples/deployment/tpu/tgi`](https://github.com/dstackai/dstack/blob/master/examples/deployment/tpu/tgi).

## Contributing

Find a mistake or can't find an important example? Raise an [issue](https://github.com/dstackai/dstack/issues) or send a [pull request](https://github.com/dstackai/dstack/tree/master/examples)!

## What's next?

1. Browse [Optimum-TPU](https://github.com/huggingface/optimum-tpu).
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services).
3. See other [TPU fine-tuning](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/tpu).
