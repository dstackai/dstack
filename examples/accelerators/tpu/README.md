# TPU

If you're using the `gcp` backend, you can use TPUs. Just specify the TPU version and the number of cores 
(separated by a dash), in the `gpu` property under `resources`. 

> Currently, only 8 TPU cores can be specified, so the supported values are `v2-8`, `v3-8`, `v4-8`, `v5litepod-8`, 
> and `v5e-8`. Multi-host TPU support, allowing for larger numbers of cores, is coming soon.

Below are a few examples on using TPUs for deployment and fine-tuning.

## Deployment

### Running as a service

 Here's an example of a [service](https://dstack.ai/docs/services) that deploys
 Llama 3.1 8B using [Optimum TPU :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu){:target="_blank"}.

<div editor-title="examples/deployment/optimum-tpu/service.dstack.yml"> 

```yaml
type: service
name: llama31-service-optimum-tpu

# Using a custom Docker image; pending on https://github.com/huggingface/optimum-tpu/pull/85
image: sjbbihan/optimum-tpu:latest
env:
  - HUGGING_FACE_HUB_TOKEN
  - MODEL_ID=meta-llama/Meta-Llama-3.1-8B
  - MAX_CONCURRENT_REQUESTS=4
  - MAX_INPUT_TOKENS=128
  - MAX_TOTAL_TOKENS=150
  - MAX_BATCH_PREFILL_TOKENS=128
commands:
  - text-generation-launcher --port 8000
port: 8000

resources:
  gpu: v5litepod-8

spot_policy: auto

model:
  format: tgi
  type: chat
  name: meta-llama/Meta-Llama-3.1-8B
```
</div>

??? info "Docker image"
    The official Docker image `huggingface/optimum-tpu:latest` doesn’t support Llama 3.1-8B. 
    We’ve created a custom image with the fix: `sjbbihan/optimum-tpu:latest`. 
    Once the [pull request :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu/pull/85){:target="_blank"} is merged, 
    the official Docker image can be used.

### Running a configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

## Fine-tuning

Below is an example of fine-tuning Llama 3.1 8B using [Optimum TPU :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu){:target="_blank"} 
and the [Abirate/english_quotes :material-arrow-top-right-thin:{ .external }](https://huggingface.co/datasets/Abirate/english_quotes){:target="_blank"}
dataset.

<div editor-title="examples/fine-tuning/optimum-tpu/llama31/train.dstack.yml"> 

```yaml
type: task
name: optimum-tpu-llama-train

python: "3.11"

env:
  - HUGGING_FACE_HUB_TOKEN
commands:
  - git clone https://github.com/Bihan/optimum-tpu.git
  - mkdir -p optimum-tpu/examples/custom/
  - cp examples/fine-tuning/optimum-tpu/llama31/train.py optimum-tpu/examples/custom/train.py
  - cp examples/fine-tuning/optimum-tpu/llama31/config.yaml optimum-tpu/examples/custom/config.yaml
  - cd optimum-tpu
  - pip install -e . -f https://storage.googleapis.com/libtpu-releases/index.html
  - pip install datasets evaluate
  - pip install accelerate -U
  - python examples/custom/train.py examples/custom/config.yaml
ports:
  - 6006

resources:
  gpu: v5litepod-8
```

</div>

[//]: # (### Fine-Tuning with TRL)
[//]: # (Use the example `examples/fine-tuning/optimum-tpu/gemma/train.dstack.yml` to Finetune `Gemma-2B` model using `trl` with `dstack` and `optimum-tpu`. )

## Dev environments

Before running a task or service, it's recommended that you first start with
a [dev environment](https://dstack.ai/docs/dev-environments). Dev environments
allow you to run commands interactively.

## Source code

The source-code of this example can be found in 
[examples/deployment/optimum-tpu :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/llama31){:target="_blank"}
and [examples/fine-tuning/optimum-tpu :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/trl){:target="_blank"}.

## Contributing

Find a mistake or can't find an important example? 
Raise an [issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues){:target="_blank"}
or send a [pull request :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}.

## What's next?

1. Browse [Optimum TPU :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu) and
   [Optimum TPU TGI :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu/tree/main/text-generation-inference).
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/fleets).
