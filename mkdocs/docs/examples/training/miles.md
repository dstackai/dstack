---
title: Miles
description: RL fine-tuning Qwen2.5-32B with Miles, SGLang, Megatron-LM, and Ray across two 8xH100 nodes
---

# Miles

This example shows how to use `dstack` and [Miles](https://github.com/radixark/miles)
to fine-tune a 32B language model with [GRPO](https://arxiv.org/abs/2402.03300)
across a multi-node cluster.
Miles uses [SGLang](https://github.com/sgl-project/sglang) for high-throughput
rollouts, [Megatron-LM](https://github.com/NVIDIA/Megatron-LM) for training,
and [Ray](https://docs.ray.io/en/latest/) to coordinate the trainer and rollout
actors across nodes.

Here we fine-tune `Qwen/Qwen2.5-32B-Instruct` on the
[GSM8K](https://huggingface.co/datasets/openai/gsm8k) dataset.

!!! info "Prerequisites"
    Before running a distributed task, make sure to create a [fleet](../../concepts/fleets.md)
    with `placement` set to [`cluster`](../../concepts/fleets.md#cluster-placement).

## Run a Ray cluster

### Define a configuration

The [task](../../concepts/tasks.md) below starts Ray on two nodes and prepares
each node by downloading the model and dataset, then converting the checkpoint
to Megatron's `torch_dist` format.

<div editor-title="miles-qwen32b-h100.dstack.yml">

```yaml
type: task
name: miles-qwen32b-h100
nodes: 2
image: radixark/miles:sglang-miles-v0.5.12
env:
  - WANDB_API_KEY
  - PYTHONPATH=/root/Megatron-LM
  - NCCL_DEBUG=INFO
  - MODEL_ID=Qwen/Qwen2.5-32B-Instruct
commands:
  # 1. Download the model and dataset.
  - pip install -U "huggingface_hub[cli]"
  - hf download "$MODEL_ID" --local-dir "/root/$(basename "$MODEL_ID")"
  - hf download --repo-type dataset openai/gsm8k --local-dir /root/gsm8k
  # 2. Convert the Hugging Face checkpoint to Megatron torch_dist.
  - |
    MODEL_NAME="$(basename "$MODEL_ID")"
    cd /root/miles && python tools/convert_hf_to_torch_dist.py \
      --swiglu \
      --num-layers 64 \
      --hidden-size 5120 \
      --ffn-hidden-size 27648 \
      --num-attention-heads 40 \
      --use-rotary-position-embeddings \
      --disable-bias-linear \
      --add-qkv-bias \
      --normalization RMSNorm \
      --norm-epsilon 1e-5 \
      --rotary-base 1000000 \
      --group-query-attention \
      --num-query-groups 8 \
      --vocab-size 152064 \
      --untie-embeddings-and-output-weights \
      --hf-checkpoint "/root/$MODEL_NAME" \
      --save "/root/${MODEL_NAME}_torch_dist"
  # 3. Start Ray.
  - |
    if [ $DSTACK_NODE_RANK = 0 ]; then
      ray start --head --port=6379
    else
      ray start --address=$DSTACK_MASTER_NODE_IP:6379
    fi
ports:
  - 8265
resources:
  gpu: H100:8
  shm_size: 32GB
  disk: 1000GB..
volumes:
  - /checkpoints:/checkpoints
```

</div>

### Run the configuration

Run the task with [`dstack apply`](../../reference/cli/dstack/apply.md). By
default, `dstack apply` forwards the Ray dashboard port to `localhost:8265`.

<div class="termy">

```shell
$ export WANDB_API_KEY=...
$ dstack apply -f miles-qwen32b-h100.dstack.yml
```

</div>

While `dstack apply` is attached, you can submit Ray jobs through
`localhost:8265`. If you detach or run from another machine, use
[`dstack attach`](../../reference/cli/dstack/attach.md) to re-attach and make
the dashboard port accessible on `localhost`.

## Submit Ray jobs

Install `ray` locally before submitting jobs:

<div class="termy">

```shell
$ pip install ray
```

</div>

The submit script below runs the Miles training job on the Ray cluster. The
model is sharded across all 8 GPUs per node with tensor parallelism, and SGLang
uses the same 8 GPUs per node for rollout.

<div editor-title="submit-miles-train.sh">

```bash
#!/bin/bash
set -euo pipefail

export RAY_ADDRESS=http://localhost:8265

: "${NUM_NODES:?NUM_NODES is not set}"
: "${GPUS_PER_NODE:?GPUS_PER_NODE is not set}"

MODEL_ID="Qwen/Qwen2.5-32B-Instruct"
MODEL_NAME="$(basename "$MODEL_ID")"
HF_CHECKPOINT="/root/$MODEL_NAME"
REF_LOAD="/root/${MODEL_NAME}_torch_dist"
PROMPT_DATA="/root/gsm8k/main/train-00000-of-00001.parquet"
EVAL_PROMPT_DATA="/root/gsm8k/main/test-00000-of-00001.parquet"
INPUT_KEY="question"
LABEL_KEY="answer"
EVAL_DATASET_NAME="gsm8k"
CHECKPOINT_DIR="/checkpoints/${MODEL_NAME}-${EVAL_DATASET_NAME}"
SAVE_INTERVAL=10
WANDB_PROJECT="dstack-miles-RL"
WANDB_GROUP="${MODEL_NAME}-gsm8k-${NUM_NODES}node-${GPUS_PER_NODE}gpu"
WANDB_NAME="rollout-$(date +%Y%m%d-%H%M%S)"
ROLLOUT_GPUS_PER_ENGINE=8

CMD='cd /root/miles && python3 train.py \
  --actor-num-nodes '"$NUM_NODES"' \
  --actor-num-gpus-per-node '"$GPUS_PER_NODE"' \
  --num-gpus-per-node '"$GPUS_PER_NODE"' \
  --rollout-num-gpus-per-engine '"$ROLLOUT_GPUS_PER_ENGINE"' \
  --sglang-server-concurrency 128 \
  --colocate \
  --calculate-per-token-loss \
  --use-miles-router \
  --swiglu \
  --num-layers 64 \
  --hidden-size 5120 \
  --ffn-hidden-size 27648 \
  --num-attention-heads 40 \
  --use-rotary-position-embeddings \
  --disable-bias-linear \
  --add-qkv-bias \
  --normalization RMSNorm \
  --norm-epsilon 1e-5 \
  --rotary-base 1000000 \
  --group-query-attention \
  --num-query-groups 8 \
  --vocab-size 152064 \
  --untie-embeddings-and-output-weights \
  --hf-checkpoint '"$HF_CHECKPOINT"' \
  --ref-load '"$REF_LOAD"' \
  --prompt-data '"$PROMPT_DATA"' \
  --input-key '"$INPUT_KEY"' \
  --label-key '"$LABEL_KEY"' \
  --apply-chat-template \
  --rollout-shuffle \
  --rm-type math \
  --num-rollout 20 \
  --rollout-batch-size 8 \
  --n-samples-per-prompt 8 \
  --rollout-max-response-len 512 \
  --rollout-temperature 1 \
  --global-batch-size 64 \
  --eval-interval 5 \
  --eval-prompt-data '"$EVAL_DATASET_NAME"' '"$EVAL_PROMPT_DATA"' \
  --n-samples-per-eval-prompt 1 \
  --eval-max-response-len 512 \
  --eval-top-k 1 \
  --tensor-model-parallel-size 8 \
  --sequence-parallel \
  --pipeline-model-parallel-size 1 \
  --context-parallel-size 1 \
  --expert-model-parallel-size 1 \
  --expert-tensor-parallel-size 1 \
  --use-dynamic-batch-size \
  --max-tokens-per-gpu 9216 \
  --advantage-estimator grpo \
  --use-kl-loss \
  --kl-loss-coef 0.00 \
  --kl-loss-type low_var_kl \
  --kl-coef 0.00 \
  --entropy-coef 0.00 \
  --eps-clip 0.2 \
  --eps-clip-high 0.28 \
  --optimizer adam \
  --lr 1e-6 \
  --lr-decay-style constant \
  --weight-decay 0.1 \
  --adam-beta1 0.9 \
  --adam-beta2 0.98 \
  --sglang-mem-fraction-static 0.7 \
  --use-wandb \
  --wandb-host https://wandb.ai/ \
  --wandb-project '"$WANDB_PROJECT"' \
  --wandb-group '"$WANDB_GROUP"' \
  --wandb-exp-name '"$WANDB_NAME"' \
  --attention-dropout 0.0 \
  --hidden-dropout 0.0 \
  --accumulate-allreduce-grads-in-fp32 \
  --attention-softmax-in-fp32 \
  --attention-backend flash \
  --save '"$CHECKPOINT_DIR"' \
  --save-interval '"$SAVE_INTERVAL"''

# GLOO_SOCKET_IFNAME=eth0 is required for multi-node Gloo process group init.
# Without it, Gloo resolves to a loopback address (127.0.1.1) instead of the
# inter-node interface, causing `init_gloo_group()` to timeout.
RUNTIME_ENV_JSON=$(cat <<EOF
{
  "env_vars": {
    "PYTHONPATH": "/root/Megatron-LM",
    "CUDA_DEVICE_MAX_CONNECTIONS": "1",
    "NCCL_DEBUG": "INFO",
    "GLOO_SOCKET_IFNAME": "eth0"
  }
}
EOF
)

ray job submit \
  --address="$RAY_ADDRESS" \
  --runtime-env-json="$RUNTIME_ENV_JSON" \
  -- bash -lc "$CMD"
```

</div>

Submit the job with the same cluster shape as the task:

<div class="termy">

```shell
$ NUM_NODES=2 GPUS_PER_NODE=8 bash submit-miles-train.sh
```

</div>

!!! info "Training parameters"
    1. `--tensor-model-parallel-size 8` shards the 32B model across all 8 GPUs
       per node.
    2. `--rollout-num-gpus-per-engine 8` starts SGLang with TP-8 on each node.
    3. `--sglang-server-concurrency` sets how many requests SGLang processes
       concurrently.
    4. `--max-tokens-per-gpu 9216` sets the per-GPU token budget. Lower this if
       Megatron OOMs during training.
    5. `--sglang-mem-fraction-static 0.7` sets the SGLang KV cache memory
       fraction. Lower this if Megatron OOMs at startup.

Using Ray via `dstack` gives you access to the Ray ecosystem while benefiting
from `dstack`'s provisioning capabilities.

!!! info "What's next"
    1. Read about [distributed tasks](../../concepts/tasks.md#distributed-tasks)
       and [fleets](../../concepts/fleets.md)
    2. See the [SGLang inference](../inference/sglang.md) example
    3. Browse Miles' [examples](https://github.com/radixark/miles/tree/main/examples)
