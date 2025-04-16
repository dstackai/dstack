# AMD

`dstack` supports running dev environments, tasks, and services on AMD GPUs.
You can do that by setting up an [SSH fleet](https://dstack.ai/docs/concepts/fleets#ssh) 
with on-prem AMD GPUs or configuring a backend that offers AMD GPUs such as the `runpod` backend.

## Deployment

Most serving frameworks including vLLM and TGI have AMD support. Here's an example of a [service](https://dstack.ai/docs/services) that deploys 
Llama 3.1 70B in FP16 using [TGI :material-arrow-top-right-thin:{ .external }](https://huggingface.co/docs/text-generation-inference/en/installation_amd){:target="_blank"} and [vLLM :material-arrow-top-right-thin:{ .external }](https://docs.vllm.ai/en/latest/getting_started/amd-installation.html){:target="_blank"}.

=== "TGI"
    
    <div editor-title="examples/deployment/tgi/amd/.dstack.yml"> 
    
    ```yaml
    type: service
    name: amd-service-tgi
    
    # Using the official TGI's ROCm Docker image
    image: ghcr.io/huggingface/text-generation-inference:sha-a379d55-rocm

    env:
      - HF_TOKEN
      - MODEL_ID=meta-llama/Meta-Llama-3.1-70B-Instruct
      - TRUST_REMOTE_CODE=true
      - ROCM_USE_FLASH_ATTN_V2_TRITON=true
    commands:
      - text-generation-launcher --port 8000
    port: 8000
    # Register the model
    model: meta-llama/Meta-Llama-3.1-70B-Instruct
    
    # Uncomment to leverage spot instances
    #spot_policy: auto
    
    resources:
      gpu: MI300X
      disk: 150GB
    ```
    
    </div>


=== "vLLM"

    <div editor-title="examples/deployment/vllm/amd/.dstack.yml"> 
    
    ```yaml
    type: service
    name: llama31-service-vllm-amd
    
    # Using RunPod's ROCm Docker image
    image: runpod/pytorch:2.4.0-py3.10-rocm6.1.0-ubuntu22.04
    # Required environment variables
    env:
      - HF_TOKEN
      - MODEL_ID=meta-llama/Meta-Llama-3.1-70B-Instruct
      - MAX_MODEL_LEN=126192
    # Commands of the task
    commands:
      - export PATH=/opt/conda/envs/py_3.10/bin:$PATH
      - wget https://github.com/ROCm/hipBLAS/archive/refs/tags/rocm-6.1.0.zip
      - unzip rocm-6.1.0.zip
      - cd hipBLAS-rocm-6.1.0
      - python rmake.py
      - cd ..
      - git clone https://github.com/vllm-project/vllm.git
      - cd vllm
      - pip install triton
      - pip uninstall torch -y
      - pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.1
      - pip install /opt/rocm/share/amd_smi
      - pip install --upgrade numba scipy huggingface-hub[cli]
      - pip install "numpy<2"
      - pip install -r requirements-rocm.txt
      - wget -N https://github.com/ROCm/vllm/raw/fa78403/rocm_patch/libamdhip64.so.6 -P /opt/rocm/lib
      - rm -f "$(python3 -c 'import torch; print(torch.__path__[0])')"/lib/libamdhip64.so*
      - export PYTORCH_ROCM_ARCH="gfx90a;gfx942"
      - wget https://dstack-binaries.s3.amazonaws.com/vllm-0.6.0%2Brocm614-cp310-cp310-linux_x86_64.whl
      - pip install vllm-0.6.0+rocm614-cp310-cp310-linux_x86_64.whl
      - vllm serve $MODEL_ID --max-model-len $MAX_MODEL_LEN --port 8000
    # Service port
    port: 8000
    # Register the model
    model: meta-llama/Meta-Llama-3.1-70B-Instruct
    
    # Uncomment to leverage spot instances
    #spot_policy: auto
    
    resources:
      gpu: MI300X
      disk: 200GB
    ```
    </div>

    Note, maximum size of vLLM’s `KV cache` is 126192, consequently we must set `MAX_MODEL_LEN` to 126192. Adding `/opt/conda/envs/py_3.10/bin` to PATH ensures we use the Python 3.10 environment necessary for the pre-built binaries compiled specifically for this version.
    
    > To speed up the `vLLM-ROCm` installation, we use a pre-built binary from S3. 
    > You can find the task to build and upload the binary in 
    > [`examples/deployment/vllm/amd/` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/vllm/amd/){:target="_blank"}.

!!! info "Docker image"
    If you want to use AMD, specifying `image` is currently required. This must be an image that includes
    ROCm drivers.

To request multiple GPUs, specify the quantity after the GPU name, separated by a colon, e.g., `MI300X:4`.

## Fine-tuning

=== "TRL"

    Below is an example of LoRA fine-tuning Llama 3.1 8B using [TRL :material-arrow-top-right-thin:{ .external }](https://rocm.docs.amd.com/en/latest/how-to/llm-fine-tuning-optimization/single-gpu-fine-tuning-and-inference.html){:target="_blank"} 
    and the [`mlabonne/guanaco-llama2-1k` :material-arrow-top-right-thin:{ .external }](https://huggingface.co/datasets/mlabonne/guanaco-llama2-1k){:target="_blank"}
    dataset.
    
    <div editor-title="examples/fine-tuning/trl/amd/.dstack.yml">
    
    ```yaml
    type: task
    name: trl-amd-llama31-train
    
    # Using RunPod's ROCm Docker image
    image: runpod/pytorch:2.1.2-py3.10-rocm6.1-ubuntu22.04

    # Required environment variables
    env:
      - HF_TOKEN
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
      - python examples/fine-tuning/trl/amd/train.py
    
    # Uncomment to leverage spot instances
    #spot_policy: auto
    
    resources:
      gpu: MI300X
      disk: 150GB
    ```
    
    </div>

=== "Axolotl"
    Below is an example of fine-tuning Llama 3.1 8B using [Axolotl :material-arrow-top-right-thin:{ .external }](https://rocm.blogs.amd.com/artificial-intelligence/axolotl/README.html){:target="_blank"} 
    and the [tatsu-lab/alpaca :material-arrow-top-right-thin:{ .external }](https://huggingface.co/datasets/tatsu-lab/alpaca){:target="_blank"}
    dataset.
    
    <div editor-title="examples/fine-tuning/axolotl/amd/.dstack.yml">
    
    ```yaml
    type: task
    # The name is optional, if not specified, generated randomly
    name: axolotl-amd-llama31-train

    # Using RunPod's ROCm Docker image
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

    Note, to support ROCm, we need to checkout to commit `d4f6c65`. This commit eliminates the need to manually modify the Axolotl source code to make xformers compatible with ROCm, as described in the [xformers workaround :material-arrow-top-right-thin:{ .external }](https://docs.axolotl.ai/docs/amd_hpc.html#apply-xformers-workaround). This installation approach is also followed for building Axolotl ROCm docker image. [(See Dockerfile) :material-arrow-top-right-thin:{ .external }](https://github.com/ROCm/rocm-blogs/blob/release/blogs/artificial-intelligence/axolotl/src/Dockerfile.rocm){:target="_blank"}.

    > To speed up installation of `flash-attention` and `xformers `, we use pre-built binaries uploaded to S3. 
    > You can find the tasks that build and upload the binaries
    > in [`examples/fine-tuning/axolotl/amd/` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl/amd/){:target="_blank"}.

## Running a configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ WANDB_PROJECT=...
$ WANDB_NAME=axolotl-amd-llama31-train
$ HUB_MODEL_ID=...
$ dstack apply -f examples/deployment/vllm/amd/.dstack.yml
```

</div>

## Source code

The source-code of this example can be found in 
[`examples/deployment/tgi/amd` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/tgi/amd){:target="_blank"},
[`examples/deployment/vllm/amd` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/vllm/amd){:target="_blank"},
[`examples/fine-tuning/axolotl/amd` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl/amd){:target="_blank"} and
[`examples/fine-tuning/trl/amd` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/trl/amd){:target="_blank"}

## What's next?

1. Browse [TGI :material-arrow-top-right-thin:{ .external }](https://rocm.docs.amd.com/en/latest/how-to/rocm-for-ai/deploy-your-model.html#serving-using-hugging-face-tgi),
   [vLLM :material-arrow-top-right-thin:{ .external }](https://docs.vllm.ai/en/latest/getting_started/amd-installation.html#build-from-source-rocm),
   [Axolotl :material-arrow-top-right-thin:{ .external }](https://github.com/ROCm/rocm-blogs/tree/release/blogs/artificial-intelligence/axolotl),
   [TRL :material-arrow-top-right-thin:{ .external }](https://rocm.docs.amd.com/en/latest/how-to/llm-fine-tuning-optimization/fine-tuning-and-inference.html) and
   [ROCm Bitsandbytes :material-arrow-top-right-thin:{ .external }](https://github.com/ROCm/bitsandbytes)
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), and
   [services](https://dstack.ai/docs/services).
