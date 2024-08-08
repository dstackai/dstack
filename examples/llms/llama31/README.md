# Llama 3.1

This example walks you through how to use Llama 3.1 for inference and fine-tuning with `dstack`, whether in the cloud or
on-prem.

## Inference

### Memory requirements

Below are the approximate memory requirements for loading the model. 
This excludes memory for the model context and CUDA kernel reservations.

| Model size | FP16  | FP8   | INT4  |
|------------|-------|-------|-------|
| **8B**     | 16GB  | 8GB   | 4GB   |
| **70B**    | 140GB | 70GB  | 35GB  |
| **405B**   | 810GB | 405GB | 203GB |

For example, the FP16 version of Llama 3.1 405B won't fit into a single machine with eight 80GB GPUs, so we'd need at least two
nodes.

### Running as a task

If you'd like to run Llama 3.1 for development purposes, consider using `dstack` tasks. 
You can use any serving framework, such as vLLM, TGI, or Ollama.

=== "vLLM"

    <div editor-title="examples/llms/llama31/vllm/task.dstack.yml"> 

    ```yaml
    type: task
    name: llama31-task-vllm
    
    python: "3.10"
    
    env:
      - HUGGING_FACE_HUB_TOKEN
      - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
      - MAX_MODE_LEN=4096
    commands:
      - pip install vllm
      - vllm serve $MODEL_ID
        --tensor-parallel-size $DSTACK_GPUS_NUM
        --max-model-len $MAX_MODEL_LEN
    ports: [8000]
    
    # Use either spot or on-demand instances
    spot_policy: auto
    
    resources:
      # Required resources
      gpu: 24GB
      # Shared memory (required by multi-gpu)
      shm_size: 24GB
    ```

    </div>

=== "TGI"

    <div editor-title="examples/llms/llama31/tgi/task.dstack.yml"> 

    ```yaml
    type: task
    name: llama31-task-tgi
    
    image: ghcr.io/huggingface/text-generation-inference:latest
    
    env:
      - HUGGING_FACE_HUB_TOKEN
      - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
      - MAX_INPUT_LENGTH=4000
      - MAX_TOTAL_TOKENS=4096
    commands:
      - NUM_SHARD=$DSTACK_GPUS_NUM text-generation-launcher
    ports: [80]
    
    # Use either spot or on-demand instances
    spot_policy: auto
    
    resources:
      # Required resources
      gpu: 24GB
      # Shared memory (required by multi-gpu)
      shm_size: 24GB
    ```

    </div>

=== "Ollama"

    <div editor-title="examples/llms/llama31/ollama/task.dstack.yml"> 

    ```yaml
    type: task
    name: llama31-task-ollama    

    image: ollama/ollama
    commands:
      - ollama serve &
      - sleep 3
      - ollama pull llama3.1
      - fg
    port: 11434
    
    resources:
      gpu: 24GB

    # Use either spot or on-demand instances
    spot_policy: auto
    
    # Required resources
    resources:
      gpu: 24GB
    ```

    </div>

Note, when using Llama 3.1 8B with a 24GB GPU, we must limit the context size to 4096 tokens to fit the memory.

### Quantization

The INT4 version of Llama 3.1 70B, can fit into two 40GB GPUs.

[//]: # (TODO: Example: INT4 / 70B / 40GB:2)

The INT4 version of Llama 3.1 405B can fit into eight 40GB GPUs.

[//]: # (TODO: Example: INT4 / 405B / 40GB:8)

Useful links:

 * [Meta's official FP8 quantized version of Llama 3.1 405B](https://huggingface.co/meta-llama/Meta-Llama-3.1-405B-Instruct-FP8) (with minimal accuracy degradation)
 * [Llama 3.1 Quantized Models](https://huggingface.co/collections/hugging-quants/llama-31-gptq-awq-and-bnb-quants-669fa7f50f6e713fd54bd198) with quantized checkpoints

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/index.md#dstack-apply) command.

<div class="termy">

```shell
$ HUGGING_FACE_HUB_TOKEN=...

$ dstack apply -f examples/llms/llama31/vllm/task.dstack.yml

 #  BACKEND  REGION    RESOURCES                    SPOT  PRICE
 1  runpod   CA-MTL-1  18xCPU, 100GB, A5000:24GB    yes   $0.12
 2  runpod   EU-SE-1   18xCPU, 100GB, A5000:24GB    yes   $0.12
 3  gcp      us-west4  27xCPU, 150GB, A5000:24GB:2  yes   $0.23
 
Submit the run llama31-task-vllm? [y/n]: y

Provisioning...
---> 100%
```

</div>

If you run a task, `dstack apply` automatically forwards the remote ports to `localhost` for convenient access.

<div class="termy">

```shell
$ curl 127.0.0.1:8001/v1/chat/completions \
    -X POST \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
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
      "max_tokens": 128
    }'
```

</div>

[//]: # (TODO: How to prompting and tool calling)

### Deploying as a service

If you'd like to deploy Llama 3.1 as public auto-scalable and secure endpoint,
consider using `dstack` [services](https://dstack.ai/docs/services).

[//]: # (TODO: Include an example)

[//]: # (TODO: Syntetic data generation)

## Fine-tuning with TRL

### Memory requirements

Below are the approximate memory requirements for fine-tuning Llama 3.1.

| Model size | Full fine-tuning | LoRA  | QLoRA |
|------------|------------------|-------|-------|
| **8B**     | 60GB             | 16GB  | 6GB   |
| **70B**    | 500GB            | 160GB | 48GB  |
| **405B**   | 3.25TB           | 950GB | 250GB |

The requirements can be significantly reduced with certain optimizations.

### Running on multiple GPUs

Below is an example for fine-tuning Llama 3.1 8B on
OpenAssistant’s [chat dataset](https://huggingface.co/datasets/OpenAssistant/oasst_top1_2023-08-25):

<div editor-title="examples/fine-tuning/trl/train.dstack.yml"> 

```yaml
type: task
name: trl-train

python: "3.10"
# Ensure nvcc is installed (req. for Flash Attention) 
nvcc: true

env:
  - HUGGING_FACE_HUB_TOKEN
  - WANDB_API_KEY
commands:
  - pip install "transformers>=4.43.2"
  - pip install bitsandbytes
  - pip install flash-attn --no-build-isolation
  - pip install peft
  - pip install wandb
  - git clone https://github.com/huggingface/trl
  - cd trl
  - pip install .
  - accelerate launch
    --config_file=examples/accelerate_configs/multi_gpu.yaml
    --num_processes $DSTACK_GPUS_PER_NODE 
    examples/scripts/sft.py
    --model_name meta-llama/Meta-Llama-3.1-8B
    --dataset_name OpenAssistant/oasst_top1_2023-08-25
    --dataset_text_field="text"
    --per_device_train_batch_size 1
    --per_device_eval_batch_size 1
    --gradient_accumulation_steps 4
    --learning_rate 2e-4
    --report_to wandb
    --bf16
    --max_seq_length 1024
    --lora_r 16 --lora_alpha 32
    --lora_target_modules q_proj k_proj v_proj o_proj
    --load_in_4bit
    --use_peft
    --attn_implementation "flash_attention_2"
    --logging_steps=10
    --output_dir models/llama31
    --hub_model_id peterschmidt85/FineLlama-3.1-8B

resources:
gpu:
  # 24GB or more vRAM
  memory: 24GB..
  # One or more GPU
  count: 1..
# Shared memory (for multi-gpu)
shm_size: 24GB
```

</div>

Change the `resources` property to specify more GPUs. 

#### DeepSpeed

For more memory-efficient use of multiple GPUs, consider using DeepSpeed and ZeRO Stage 3.

To do this, use the `examples/accelerate_configs/deepspeed_zero3.yaml` configuration file instead of 
`examples/accelerate_configs/multi_gpu.yaml`.

### Distributed training

In case the model doesn't feet into a single GPU, consider running a `dstack` task on multiple nodes.

<div editor-title="examples/fine-tuning/trl/train.dstack.yml"> 

```yaml
type: task
name: trl-train-distrib

# Size of the cluster
nodes: 2
# Ensure nvcc is installed (req. for Flash Attention) 
nvcc: true

python: "3.10"

env:
  - HUGGING_FACE_HUB_TOKEN
  - WANDB_API_KEY
commands:
  - pip install "transformers>=4.43.2"
  - pip install bitsandbytes
  - pip install flash-attn --no-build-isolation
  - pip install peft
  - pip install wandb
  - git clone https://github.com/huggingface/trl
  - cd trl
  - pip install .
  - accelerate launch
    --config_file=examples/accelerate_configs/fsdp_qlora.yaml 
    --main_process_ip=$DSTACK_MASTER_NODE_IP
    --main_process_port=8008
    --machine_rank=$DSTACK_NODE_RANK
    --num_processes=$DSTACK_GPUS_NUM
    --num_machines=$DSTACK_NODES_NUM
      examples/scripts/sft.py
    --model_name meta-llama/Meta-Llama-3.1-8B
    --dataset_name OpenAssistant/oasst_top1_2023-08-25
    --dataset_text_field="text"
    --per_device_train_batch_size 1
    --per_device_eval_batch_size 1
    --gradient_accumulation_steps 4
    --learning_rate 2e-4
    --report_to wandb
    --bf16
    --max_seq_length 1024
    --lora_r 16 --lora_alpha 32
    --lora_target_modules q_proj k_proj v_proj o_proj
    --load_in_4bit
    --use_peft
    --attn_implementation "flash_attention_2"
    --logging_steps=10
    --output_dir models/llama31
    --hub_model_id peterschmidt85/FineLlama-3.1-8B
    --torch_dtype bfloat16
    --use_bnb_nested_quant

resources:
  gpu:
    # 24GB or more vRAM
    memory: 24GB..
    # One or more GPU
    count: 1..
  # Shared memory (for multi-gpu)
  shm_size: 24GB
```

</div>

[//]: # (TODO: Find a better example for a multi-node training)

## Fleets

By default, `dstack run` reuses `idle` instances from one of the existing [fleets](https://dstack.ai/docs/fleets).
If no `idle` instances meet the requirements, it creates a new fleet using one of the configured backends.

Use [fleets](https://dstack.ai/docs/fleets.md) configurations to create fleets manually. This reduces startup time for dev environments,
tasks, and services, and is very convenient if you want to reuse fleets across runs.

## Dev environments

Before running a task or service, it's recommended that you first start with
a [dev environment](https://dstack.ai/docs/dev-environments). Dev environments
allow you to run commands interactively.

## Source code

The source-code of this example can be found in 
[examples/llms/llama31](https://github.com/dstackai/dstack/blob/master/examples/llms/llama31)
and [examples/fine-tuning/trl](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/trl).

## Contributing

Find a mistake or can't find an important example? 
Raise an [issue](https://github.com/dstackai/dstack/issues) or send a [pull request](https://github.com/dstackai/dstack/tree/master/examples).

## What's next?

1. Browse [Llama 3.1 on HuggingFace :material-arrow-top-right-thin:{ .external }](https://huggingface.co/collections/meta-llama/llama-31-669fc079a0c406a149a5738f), 
   [HuggingFace's Llama recipes :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/huggingface-llama-recipes), 
   [Meta's Llama recipes :material-arrow-top-right-thin:{ .external }](https://github.com/meta-llama/llama-recipes) 
   and [Llama Agentic System :material-arrow-top-right-thin:{ .external }](https://github.com/meta-llama/llama-agentic-system/).
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/fleets).
