# TPU

If you're using the `gcp` backend, you can use TPUs. Just specify the TPU version and the number of cores 
(separated by a dash), in the `gpu` property under `resources`. 

> Currently, maximum 8 TPU cores can be specified, so the maximum supported values are `v2-8`, `v3-8`, `v4-8`, `v5litepod-8`, 
> and `v5e-8`. Multi-host TPU support, allowing for larger numbers of cores, is coming soon.

Below are a few examples on using TPUs for deployment and fine-tuning.

## Deployment

You can use any serving framework, such as vLLM, TGI. Here's an example of a [service](https://dstack.ai/docs/services) that deploys
Llama 3.1 8B using 
[Optimum TPU :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu){:target="_blank"}
and [vLLM :material-arrow-top-right-thin:{ .external }](https://github.com/vllm-project/vllm){:target="_blank"}.

=== "Optimum TPU"

    <div editor-title="examples/deployment/optimum-tpu/service.dstack.yml"> 
    
    ```yaml
    type: service
    name: llama31-service-optimum-tpu
    
    image: dstackai/optimum-tpu:llama31
    env:
      - HF_TOKEN
      - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
      - MAX_TOTAL_TOKENS=4096
      - MAX_BATCH_PREFILL_TOKENS=4095
    commands:
      - text-generation-launcher --port 8000
    port: 8000
    
    spot_policy: auto
    resources:
      gpu: v5litepod-4 
    
    model:
      format: tgi
      type: chat
      name: meta-llama/Meta-Llama-3.1-8B-Instruct
    ```
    </div>

    Note, for `Optimum TPU` by default `MAX_INPUT_TOKEN` is set to 4095, consequently we must set `MAX_BATCH_PREFILL_TOKENS` to 4095.

    ??? info "Docker image"
        The official Docker image `huggingface/optimum-tpu:latest` doesn’t support Llama 3.1-8B. 
        We’ve created a custom image with the fix: `dstackai/optimum-tpu:llama31`. 
        Once the [pull request :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu/pull/87){:target="_blank"} is merged, 
        the official Docker image can be used.

=== "vLLM"
    <div editor-title="examples/deployment/vllm/service-tpu.dstack.yml"> 
    
    ```yaml
    type: service
    name: llama31-service-vllm-tpu

    env:
      - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
      - HF_TOKEN
      - DATE=20240828
      - TORCH_VERSION=2.5.0
      - VLLM_TARGET_DEVICE=tpu
      - MAX_MODEL_LEN=4096
    commands:
      - pip install https://storage.googleapis.com/pytorch-xla-releases/wheels/tpuvm/torch-${TORCH_VERSION}.dev${DATE}-cp311-cp311-linux_x86_64.whl
      - pip3 install https://storage.googleapis.com/pytorch-xla-releases/wheels/tpuvm/torch_xla-${TORCH_VERSION}.dev${DATE}-cp311-cp311-linux_x86_64.whl
      - pip install torch_xla[tpu] -f https://storage.googleapis.com/libtpu-releases/index.html
      - pip install torch_xla[pallas] -f https://storage.googleapis.com/jax-releases/jax_nightly_releases.html -f https://storage.googleapis.com/jax-releases/jaxlib_nightly_releases.html
      - git clone https://github.com/vllm-project/vllm.git
      - cd vllm
      - pip install -r requirements-tpu.txt
      - apt-get install -y libopenblas-base libopenmpi-dev libomp-dev
      - python setup.py develop
      - vllm serve $MODEL_ID 
          --tensor-parallel-size 4 
          --max-model-len $MAX_MODEL_LEN
          --port 8000
    port:
      - 8000

    spot_policy: auto
    resources:
      gpu: v5litepod-4

    model:
      format: openai
      type: chat
      name: meta-llama/Meta-Llama-3.1-8B-Instruct
    ```
    </div>

    Note, when using Llama 3.1 8B with a `v5litepod` which has 16GB memory per core, we must limit the context size to 4096 tokens to fit the memory.

### Memory requirements

Below are the approximate memory requirements for serving LLMs with their corresponding TPUs. 

| Model size | bfloat16 | TPU          | int8  | TPU            |
|------------|----------|--------------|-------|----------------|
| **8B**     | 16GB     | v5litepod-4  | 8GB   | v5litepod-4    |
| **70B**    | 140GB    | v5litepod-16 | 70GB  | v5litepod-16   |
| **405B**   | 810GB    | v5litepod-64 | 405GB | v5litepod-64   |

Note, `v5litepod` is optimized for serving transformer-based models. Each core is equipped with 16GB of memory.

### Supported frameworks

| Framework | Quantization   | Note                                                                                                                                                                                                                                                                                             |
|-----------|----------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **TGI**   | bfloat16       | To deploy with TGI, Optimum TPU must be used.                                                                                                                                                                                                                                                    |
| **vLLM**  | int8, bfloat16 | int8 quantization still requires the same memory because the weights are first moved to the TPU in bfloat16, and then converted to int8. See the [pull request :material-arrow-top-right-thin:{ .external }](https://github.com/vllm-project/vllm/pull/7005){:target="_blank"} for more details. |

### Running a configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

## Fine-tuning with Optimum TPU

Below is an example of fine-tuning Llama 3.1 8B using [Optimum TPU :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu){:target="_blank"} 
and the [Abirate/english_quotes :material-arrow-top-right-thin:{ .external }](https://huggingface.co/datasets/Abirate/english_quotes){:target="_blank"}
dataset.

<div editor-title="examples/fine-tuning/optimum-tpu/llama31/train.dstack.yml"> 

```yaml
type: task
name: optimum-tpu-llama-train

python: "3.11"

env:
  - HF_TOKEN
commands:
  - git clone -b add_llama_31_support https://github.com/dstackai/optimum-tpu.git
  - mkdir -p optimum-tpu/examples/custom/
  - cp examples/fine-tuning/optimum-tpu/llama31/train.py optimum-tpu/examples/custom/train.py
  - cp examples/fine-tuning/optimum-tpu/llama31/config.yaml optimum-tpu/examples/custom/config.yaml
  - cd optimum-tpu
  - pip install -e . -f https://storage.googleapis.com/libtpu-releases/index.html
  - pip install datasets evaluate
  - pip install accelerate -U
  - pip install peft
  - python examples/custom/train.py examples/custom/config.yaml


resources:
  gpu: v5litepod-8
```

</div>

[//]: # (### Fine-Tuning with TRL)
[//]: # (Use the example `examples/fine-tuning/optimum-tpu/gemma/train.dstack.yml` to Finetune `Gemma-2B` model using `trl` with `dstack` and `optimum-tpu`. )

### Memory requirements

Below are the approximate memory requirements for fine-tuning LLMs with their corresponding TPUs.

| Model size | LoRA  | TPU          |
|------------|-------|--------------|
| **8B**     | 16GB  | v5litepod-8  |
| **70B**    | 160GB | v5litepod-16 |
| **405B**   | 950GB | v5litepod-64 |

Note, `v5litepod` is optimized for fine-tuning transformer-based models. Each core is equipped with 16GB of memory.

### Supported frameworks

| Framework       | Quantization | Note                                                                                              |
|-----------------|--------------|---------------------------------------------------------------------------------------------------|
| **TRL**         | bfloat16     | To fine-tune using TRL, Optimum TPU is recommended. TRL doesn't support Llama 3.1 out of the box. |
| **Pytorch XLA** | bfloat16     |                                                                                                   |

## Dev environments

Before running a task or service, it's recommended that you first start with
a [dev environment](https://dstack.ai/docs/dev-environments). Dev environments
allow you to run commands interactively.

## Source code

The source-code of this example can be found in 
[`examples/deployment/optimum-tpu` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/llama31){:target="_blank"}
and [`examples/fine-tuning/optimum-tpu` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/trl){:target="_blank"}.

## What's next?

1. Browse [Optimum TPU :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu),
   [Optimum TPU TGI :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu/tree/main/text-generation-inference) and
   [vLLM :material-arrow-top-right-thin:{ .external }](https://docs.vllm.ai/en/latest/getting_started/tpu-installation.html).
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/concepts/fleets).
