---
title: AMD
description: Deploying and fine-tuning models on AMD MI300X GPUs using SGLang, vLLM, TRL, and Axolotl
---

# AMD

`dstack` supports running dev environments, tasks, and services on AMD GPUs.
You can do that by setting up an [SSH fleet](https://dstack.ai/docs/concepts/fleets#ssh-fleets)
with on-prem AMD GPUs or configuring a backend that offers AMD GPUs such as the `runpod` backend.

## Deployment

Here are examples of a [service](https://dstack.ai/docs/services) that deploy
`Qwen/Qwen3.6-27B` on AMD MI300X GPUs using
[SGLang](https://github.com/sgl-project/sglang) and
[vLLM](https://docs.vllm.ai/en/latest/).

=== "SGLang"

    <div editor-title="service.dstack.yml">

    ```yaml
    type: service
    name: qwen36-service-sglang-amd

    image: lmsysorg/sglang:v0.5.10-rocm720-mi30x

    commands:
      - |
        sglang serve \
          --model-path Qwen/Qwen3.6-27B \
          --host 0.0.0.0 \
          --port 30000 \
          --tp $DSTACK_GPUS_NUM \
          --reasoning-parser qwen3 \
          --mem-fraction-static 0.8 \
          --context-length 262144

    port: 30000
    model: Qwen/Qwen3.6-27B

    volumes:
      - instance_path: /root/.cache
        path: /root/.cache
        optional: true

    resources:
      cpu: 52..
      memory: 896GB..
      shm_size: 16GB
      disk: 450GB..
      gpu: MI300X:4
    ```

    </div>

=== "vLLM"

    <div editor-title="service.dstack.yml">

    ```yaml
    type: service
    name: qwen36-service-vllm-amd

    image: vllm/vllm-openai-rocm:v0.19.1

    commands:
      - |
        vllm serve Qwen/Qwen3.6-27B \
          --host 0.0.0.0 \
          --port 8000 \
          --tensor-parallel-size $DSTACK_GPUS_NUM \
          --max-model-len 262144 \
          --reasoning-parser qwen3

    port: 8000
    model: Qwen/Qwen3.6-27B

    volumes:
      - instance_path: /root/.cache
        path: /root/.cache
        optional: true

    resources:
      cpu: 52..
      memory: 896GB..
      shm_size: 16GB
      disk: 450GB..
      gpu: MI300X:4
    ```

    </div>

!!! info "Docker image"
    AMD deployments require specifying an image that already includes ROCm
    drivers. The SGLang and vLLM examples above use pinned ROCm images.

To request multiple GPUs, specify the quantity after the GPU name, separated by a colon, e.g., `MI300X:4`.

If you're using multiple AMD nodes, validate cluster networking with the
[NCCL/RCCL tests](https://dstack.ai/examples/clusters/nccl-rccl-tests/) example.

## Fine-tuning

=== "TRL"

    Below is an example of LoRA fine-tuning Llama 3.1 8B using [TRL](https://rocm.docs.amd.com/en/latest/how-to/llm-fine-tuning-optimization/single-gpu-fine-tuning-and-inference.html)
    and the [`mlabonne/guanaco-llama2-1k`](https://huggingface.co/datasets/mlabonne/guanaco-llama2-1k)
    dataset.

    <div editor-title="train.dstack.yml">

    ```yaml
    type: task
    name: trl-amd-llama31-train

    # Using Runpod's ROCm Docker image
    image: runpod/pytorch:2.1.2-py3.10-rocm6.1-ubuntu22.04

    # Required environment variables
    env:
      - HF_TOKEN
    # Mount files
    files:
      - train.py
    # Commands of the task
    commands:
      - export PATH=/opt/conda/envs/py_3.10/bin:$PATH
      - git clone https://github.com/ROCm/bitsandbytes
      - cd bitsandbytes
      - git checkout rocm_enabled
      - pip install -r requirements-dev.txt
      - cmake -DBNB_ROCM_ARCH="gfx942" -DCOMPUTE_BACKEND=hip -S  .
      - make
      - pip install .
      - pip install trl
      - pip install peft
      - pip install transformers datasets huggingface-hub scipy
      - cd ..
      - python train.py

    # Uncomment to leverage spot instances
    #spot_policy: auto

    resources:
      gpu: MI300X
      disk: 150GB
    ```

    </div>

=== "Axolotl"
    Below is an example of fine-tuning Llama 3.1 8B using [Axolotl](https://rocm.blogs.amd.com/artificial-intelligence/axolotl/README.html)
    and the [tatsu-lab/alpaca](https://huggingface.co/datasets/tatsu-lab/alpaca)
    dataset.

    <div editor-title="train.dstack.yml">

    ```yaml
    type: task
    # The name is optional, if not specified, generated randomly
    name: axolotl-amd-llama31-train

    # Using Runpod's ROCm Docker image
    image: runpod/pytorch:2.1.2-py3.10-rocm6.0.2-ubuntu22.04
    # Required environment variables
    env:
      - HF_TOKEN
      - WANDB_API_KEY
      - WANDB_PROJECT
      - WANDB_NAME=axolotl-amd-llama31-train
      - HUB_MODEL_ID
    # Commands of the task
    commands:
      - export PATH=/opt/conda/envs/py_3.10/bin:$PATH
      - pip uninstall torch torchvision torchaudio -y
      - python3 -m pip install --pre torch==2.3.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.0/
      - git clone https://github.com/OpenAccess-AI-Collective/axolotl
      - cd axolotl
      - git checkout d4f6c65
      - pip install -e .
      # Latest pynvml is not compatible with axolotl commit d4f6c65, so we need to fall back to version 11.5.3
      - pip uninstall pynvml -y
      - pip install pynvml==11.5.3
      - cd ..
      - wget https://dstack-binaries.s3.amazonaws.com/flash_attn-2.0.4-cp310-cp310-linux_x86_64.whl
      - pip install flash_attn-2.0.4-cp310-cp310-linux_x86_64.whl
      - wget https://dstack-binaries.s3.amazonaws.com/xformers-0.0.26-cp310-cp310-linux_x86_64.whl
      - pip install xformers-0.0.26-cp310-cp310-linux_x86_64.whl
      - git clone --recurse https://github.com/ROCm/bitsandbytes
      - cd bitsandbytes
      - git checkout rocm_enabled
      - pip install -r requirements-dev.txt
      - cmake -DBNB_ROCM_ARCH="gfx942" -DCOMPUTE_BACKEND=hip -S  .
      - make
      - pip install .
      - cd ..
      - accelerate launch -m axolotl.cli.train -- axolotl/examples/llama-3/fft-8b.yaml
              --wandb-project "$WANDB_PROJECT"
              --wandb-name "$WANDB_NAME"
              --hub-model-id "$HUB_MODEL_ID"

    resources:
      gpu: MI300X
      disk: 150GB
    ```
    </div>

    Note, to support ROCm, we need to checkout to commit `d4f6c65`. This commit eliminates the need to manually modify the Axolotl source code to make xformers compatible with ROCm, as described in the [xformers workaround](https://docs.axolotl.ai/docs/amd_hpc.html#apply-xformers-workaround). This installation approach is also followed for building Axolotl ROCm docker image. [(See Dockerfile)](https://github.com/ROCm/rocm-blogs/blob/release/blogs/artificial-intelligence/axolotl/src/Dockerfile.rocm).

    > To speed up installation of `flash-attention` and `xformers`, we use pre-built binaries uploaded to S3.

## Running a configuration

Once a configuration is ready, save it to a `.dstack.yml` file. If your
configuration references environment variables such as `HF_TOKEN` or
`WANDB_API_KEY`, export them first. Then run
`dstack apply -f <configuration file>`, and `dstack` will automatically
provision the cloud resources and run the configuration.

<div class="termy">

```shell
$ dstack apply -f <configuration file>
```

</div>

## What's next?

1. Browse the dedicated [SGLang](https://dstack.ai/examples/inference/sglang/)
   and [vLLM](https://dstack.ai/examples/inference/vllm/) examples, plus
   [Axolotl](https://github.com/ROCm/rocm-blogs/tree/release/blogs/artificial-intelligence/axolotl),
   [TRL](https://rocm.docs.amd.com/en/latest/how-to/llm-fine-tuning-optimization/fine-tuning-and-inference.html),
   and [ROCm Bitsandbytes](https://github.com/ROCm/bitsandbytes)
2. Run [NCCL/RCCL tests](https://dstack.ai/examples/clusters/nccl-rccl-tests/)
   to validate multi-node AMD cluster networking.
3. Check [dev environments](https://dstack.ai/docs/dev-environments),
   [tasks](https://dstack.ai/docs/tasks), and
   [services](https://dstack.ai/docs/services).
