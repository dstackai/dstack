# Deepseek

This example walks you through how to deploy and
train [Deepseek](https://huggingface.co/deepseek-ai)
models with `dstack`.

> We used Deepseek-R1 distilled models and Deepseek-V2-Lite, a 16B model with the same architecture as Deepseek-R1 (671B). Deepseek-V2-Lite retains MLA and DeepSeekMoE but requires less memory, making it ideal for testing and fine-tuning on smaller GPUs.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo with examples.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    ```
    </div>

## Deployment

### AMD

Here's an example of a service that deploys `Deepseek-R1-Distill-Llama-70B` using [SGLang](https://github.com/sgl-project/sglang) and [vLLM](https://github.com/vllm-project/vllm) with AMD `MI300X` GPU. The below configurations also support `Deepseek-V2-Lite`.

=== "SGLang"

    <div editor-title="examples/llms/deepseek/sglang/amd/.dstack.yml">

    ```yaml
    type: service
    name: deepseek-r1-amd

    image: lmsysorg/sglang:v0.4.1.post4-rocm620
    env:
      - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Llama-70B
    commands:
       - python3 -m sglang.launch_server
         --model-path $MODEL_ID
         --port 8000
         --trust-remote-code

    port: 8000
    model: deepseek-ai/DeepSeek-R1-Distill-Llama-70B

    resources:
      gpu: MI300X
      disk: 300Gb

    ```
    </div>

=== "vLLM"

    <div editor-title="examples/llms/deepseek/sglang/amd/.dstack.yml">

    ```yaml
    type: service
    name: deepseek-r1-amd

    image: rocm/vllm:rocm6.2_mi300_ubuntu20.04_py3.9_vllm_0.6.4
    env:
      - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Llama-70B
      - MAX_MODEL_LEN=126432
    commands:
      - vllm serve $MODEL_ID
        --max-model-len $MAX_MODEL_LEN
        --trust-remote-code
    port: 8000

    model: deepseek-ai/DeepSeek-R1-Distill-Llama-70B

    resources:
      gpu: MI300X
      disk: 300Gb
    ```
    </div>

Note, when using `Deepseek-R1-Distill-Llama-70B` with `vLLM` with a 192GB GPU, we must limit the context size to 126432 tokens to fit the memory.

### NVIDIA

Here's an example of a service that deploys `Deepseek-R1-Distill-Llama-8B`
using [SGLang](https://github.com/sgl-project/sglang)
and [vLLM](https://github.com/vllm-project/vllm) with NVIDIA GPUs.
Both SGLang and vLLM also support `Deepseek-V2-Lite`.

=== "SGLang"
    <div editor-title="examples/llms/deepseek/sglang/nvidia/.dstack.yml">

    ```yaml
    type: service
    name: deepseek-r1

    image: lmsysorg/sglang:latest
    env:
      - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Llama-8B
    commands:
        - python3 -m sglang.launch_server
          --model-path $MODEL_ID
          --port 8000
          --trust-remote-code

    port: 8000
    model: deepseek-ai/DeepSeek-R1-Distill-Llama-8B

    resources:
      gpu: 24GB
    ```
    </div>

=== "vLLM"
    <div editor-title="examples/llms/deepseek/vllm/nvidia/.dstack.yml">

    ```yaml
    type: service
    name: deepseek-r1

    image: vllm/vllm-openai:latest
    env:
      - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Llama-8B
      - MAX_MODEL_LEN=4096
    commands:
      - vllm serve $MODEL_ID
        --max-model-len $MAX_MODEL_LEN
    port: 8000
    model: deepseek-ai/DeepSeek-R1-Distill-Llama-8B

    resources:
      gpu: 24GB
    ```
    </div>

Note, to run `Deepseek-R1-Distill-Llama-8B` with `vLLM` with a 24GB GPU, we must limit the context size to 4096 tokens to fit the memory.

> To run `Deepseek-V2-Lite` with `vLLM`, we must use 40GB GPU and to run `Deepseek-V2-Lite` with SGLang, we must use
> 80GB GPU. For more details on SGlang's memory requirements you can refer to
> this [issue](https://github.com/sgl-project/sglang/issues/3451).

### Memory requirements

Approximate memory requirements for loading the model (excluding context and CUDA/ROCm kernel reservations).

| Model                       | Size     | FP16   | FP8    | INT4   |
|-----------------------------|----------|--------|--------|--------|
| `Deepseek-R1`               | **671B** | 1.35TB | 671GB  | 336GB  |
| `DeepSeek-R1-Distill-Llama` | **70B**  | 161GB  | 80.5GB | 40B    |
| `DeepSeek-R1-Distill-Qwen`  | **32B**  | 74GB   | 37GB   | 18.5GB |
| `DeepSeek-V2-Lite`          | **16B**  | 35GB   | 17.5GB | 8.75GB |
| `DeepSeek-R1-Distill-Qwen`  | **14B**  | 32GB   | 16GB   | 8GB    |
| `DeepSeek-R1-Distill-Llama` | **8B**   | 18GB   | 9GB    | 4.5GB  |
| `DeepSeek-R1-Distill-Qwen`  | **7B**   | 16GB   | 8GB    | 4GB    |

For example, the FP8 version of Deepseek-R1 671B fits on a single node of MI300X with eight 192GB GPUs, a single node of
H200 with eight 141GB GPUs.

### Applying the configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ dstack apply -f examples/llms/deepseek/sglang/amd/.dstack.yml

 #  BACKEND  REGION     RESOURCES                         SPOT  PRICE
 1  runpod   EU-RO-1   24xCPU, 283GB, 1xMI300X (192GB)    no    $2.49

Submit the run deepseek-r1? [y/n]: y

Provisioning...
---> 100%
```
</div>

If no gateway is created, the service endpoint will be available at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/services/main/deepseek-r1/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
      "messages": [
        {
          "role": "system",
          "content": "You are a helpful assistant."
        },
        {
          "role": "user",
          "content": "What is Deep Learning?"
        }
      ],
      "stream": true,
      "max_tokens": 512
    }'
```
</div>

When a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured, the service endpoint will be available at `https://deepseek-r1.<gateway domain>/`.

## Fine-tuning

### AMD

Here are the examples of LoRA fine-tuning of `Deepseek-V2-Lite` and GRPO fine-tuning of `DeepSeek-R1-Distill-Qwen-1.5B` on `MI300X` GPU using HuggingFace's [TRL](https://github.com/huggingface/trl).

=== "LoRA"

    <div editor-title="examples/llms/deepseek/trl/amd/.dstack.yml">

    ```yaml
    type: task
    name: trl-train

    image: rocm/pytorch:rocm6.2.3_ubuntu22.04_py3.10_pytorch_release_2.3.0

    env:
      - WANDB_API_KEY
      - WANDB_PROJECT
      - MODEL_ID=deepseek-ai/DeepSeek-V2-Lite
      - ACCELERATE_USE_FSDP=False
    commands:
      - git clone https://github.com/huggingface/peft.git
      - pip install trl
      - pip install "numpy<2"
      - pip install peft
      - pip install wandb
      - cd peft/examples/sft
      - python train.py
        --seed 100
        --model_name_or_path "deepseek-ai/DeepSeek-V2-Lite"
        --dataset_name "smangrul/ultrachat-10k-chatml"
        --chat_template_format "chatml"
        --add_special_tokens False
        --append_concat_token False
        --splits "train,test"
        --max_seq_len 512
        --num_train_epochs 1
        --logging_steps 5
        --log_level "info"
        --logging_strategy "steps"
        --eval_strategy "epoch"
        --save_strategy "epoch"
        --hub_private_repo True
        --hub_strategy "every_save"
        --packing True
        --learning_rate 1e-4
        --lr_scheduler_type "cosine"
        --weight_decay 1e-4
        --warmup_ratio 0.0
        --max_grad_norm 1.0
        --output_dir "deepseek-sft-lora"
        --per_device_train_batch_size 8
        --per_device_eval_batch_size 8
        --gradient_accumulation_steps 4
        --gradient_checkpointing True
        --use_reentrant True
        --dataset_text_field "content"
        --use_peft_lora True
        --lora_r 16
        --lora_alpha 16
        --lora_dropout 0.05
        --lora_target_modules "all-linear"

    resources:
      gpu: MI300X
      disk: 150GB
    ```
    </div>

=== "GRPO"

    <div editor-title="examples/llms/deepseek/trl/amd/grpo.dstack.yml">
    ```yaml
    type: task
    name: trl-train-grpo

    image: rocm/pytorch:rocm6.2.3_ubuntu22.04_py3.10_pytorch_release_2.3.0

    env:
      - WANDB_API_KEY
      - WANDB_PROJECT
      - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B
    files:
      - grpo_train.py
    commands:
      - pip install trl
      - pip install datasets
      # numPy version less than 2 is required for the scipy installation with AMD.
      - pip install "numpy<2"
      - mkdir -p grpo_example
      - cp grpo_train.py grpo_example/grpo_train.py
      - cd grpo_example
      - python grpo_train.py
        --model_name_or_path $MODEL_ID
        --dataset_name trl-lib/tldr
        --per_device_train_batch_size 2
        --logging_steps 25
        --output_dir Deepseek-Distill-Qwen-1.5B-GRPO
        --trust_remote_code

    resources:
      gpu: MI300X
      disk: 150GB
    ```
    </div>

Note, the `GRPO` fine-tuning of `DeepSeek-R1-Distill-Qwen-1.5B` consumes up to 135GB of VRAM.

### NVIDIA

Here are examples of LoRA fine-tuning of `DeepSeek-R1-Distill-Qwen-1.5B` and QLoRA fine-tuning of `DeepSeek-V2-Lite`
on NVIDIA GPU using HuggingFace's [TRL](https://github.com/huggingface/trl) library.

=== "LoRA"
    <div editor-title="examples/llms/deepseek/trl/nvidia/.dstack.yml">

    ```yaml
    type: task
    name: trl-train

    python: 3.12

    env:
      - WANDB_API_KEY
      - WANDB_PROJECT
      - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B
    commands:
      - git clone https://github.com/huggingface/trl.git
      - pip install trl
      - pip install peft
      - pip install wandb
      - cd trl/trl/scripts
      - python sft.py
        --model_name_or_path $MODEL_ID
        --dataset_name trl-lib/Capybara
        --learning_rate 2.0e-4
        --num_train_epochs 1
        --packing
        --per_device_train_batch_size 2
        --gradient_accumulation_steps 8
        --gradient_checkpointing
        --logging_steps 25
        --eval_strategy steps
        --eval_steps 100
        --use_peft
        --lora_r 32
        --lora_alpha 16
        --report_to wandb
        --output_dir DeepSeek-R1-Distill-Qwen-1.5B-SFT

    resources:
      gpu: 24GB
    ```
    </div>

=== "QLoRA"
    <div editor-title="examples/llms/deepseek/trl/nvidia/deepseek_v2.dstack.yml">

    ```yaml
    type: task
    name: trl-train-deepseek-v2

    python: 3.12
    nvcc: true
    env:
      - WANDB_API_KEY
      - WANDB_PROJECT
      - MODEL_ID=deepseek-ai/DeepSeek-V2-Lite
      - ACCELERATE_USE_FSDP=False
    commands:
      - git clone https://github.com/huggingface/peft.git
      - pip install trl
      - pip install peft
      - pip install wandb
      - pip install bitsandbytes
      - cd peft/examples/sft
      - python train.py
        --seed 100
        --model_name_or_path "deepseek-ai/DeepSeek-V2-Lite"
        --dataset_name "smangrul/ultrachat-10k-chatml"
        --chat_template_format "chatml"
        --add_special_tokens False
        --append_concat_token False
        --splits "train,test"
        --max_seq_len 512
        --num_train_epochs 1
        --logging_steps 5
        --log_level "info"
        --logging_strategy "steps"
        --eval_strategy "epoch"
        --save_strategy "epoch"
        --hub_private_repo True
        --hub_strategy "every_save"
        --bf16 True
        --packing True
        --learning_rate 1e-4
        --lr_scheduler_type "cosine"
        --weight_decay 1e-4
        --warmup_ratio 0.0
        --max_grad_norm 1.0
        --output_dir "mistral-sft-lora"
        --per_device_train_batch_size 8
        --per_device_eval_batch_size 8
        --gradient_accumulation_steps 4
        --gradient_checkpointing True
        --use_reentrant True
        --dataset_text_field "content"
        --use_peft_lora True
        --lora_r 16
        --lora_alpha 16
        --lora_dropout 0.05
        --lora_target_modules "all-linear"
        --use_4bit_quantization True
        --use_nested_quant True
        --bnb_4bit_compute_dtype "bfloat16"

    resources:
      # Consumes ~25GB of VRAM for QLoRA fine-tuning deepseek-ai/DeepSeek-V2-Lite
      gpu: 48GB
    ```
    </div>

### Memory requirements

| Model                       | Size     | Full fine-tuning | LoRA  | QLoRA |
|-----------------------------|----------|------------------|-------|-------|
| `Deepseek-R1`               | **671B** | 10.5TB           | 1.4TB | 442GB |
| `DeepSeek-R1-Distill-Llama` | **70B**  | 1.09TB           | 151GB | 46GB  |
| `DeepSeek-R1-Distill-Qwen`  | **32B**  | 512GB            | 70GB  | 21GB  |
| `DeepSeek-V2-Lite`          | **16B**  | 256GB            | 35GB  | 11GB  |
| `DeepSeek-R1-Distill-Qwen`  | **14B**  | 224GB            | 30GB  | 9GB   |
| `DeepSeek-R1-Distill-Llama` | **8B**   | 128GB            | 17GB  | 5GB   |
| `DeepSeek-R1-Distill-Qwen`  | **7B**   | 112GB            | 15GB  | 4GB   |
| `DeepSeek-R1-Distill-Qwen`  | **1.5B** | 24GB             | 3.2GB | 1GB   |

The memory requirements assume low-rank update matrices are 1% of model parameters. In practice, a 7B model with QLoRA
needs 7–10GB due to intermediate hidden states.

| Fine-tuning type | Calculation                                      |
|------------------|--------------------------------------------------|
| Full fine-tuning | 671B × 16 bytes = 10.48TB                        |
| LoRA             | 671B × 2 bytes + 1% of 671B × 16 bytes = 1.41TB  |
| QLoRA(4-bit)     | 671B × 0.5 bytes + 1% of 671B × 16 bytes = 442GB |

## Source code

The source-code of this example can be found in
[`examples/llms/deepseek`](https://github.com/dstackai/dstack/blob/master/examples/llms/deepseek).

!!! info "What's next?"
    1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks),
       [services](https://dstack.ai/docs/services), and [protips](https://dstack.ai/docs/protips).
