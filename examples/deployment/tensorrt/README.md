---
title: TensorRT-LLM
description: "This example shows how to deploy Deepseek models to any cloud or on-premises environment using NVIDIA TensorRT-LLM and dstack."
---

# TensorRT-LLM
This example shows how to deploy Deepseek-R1(671B) using [TensorRT-LLM :material-arrow-top-right-thin:{ .external }](https://github.com/NVIDIA/TensorRT-LLM){:target="_blank"} and `dstack`.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), go ahead clone the repo, and run `dstack init`.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    $ dstack init
    ```
 
    </div>

## Deployment
To run DeepSeek-R1 (671B) TensorRT-LLM recommends PyTorch backend.Here's an example of a service that deploys DeepSeek-R1 (671B) using TensorRT-LLM and PyTorch backend.

<div editor-title="examples/deployment/tensorrt/.dstack.yml">

```yaml
type: service
name: deepseek-r1
# Use dstack task in examples/deployment/tensorrt/build.trtllm.yml to build docker image.
image: dstackai/tensorrt_llm:latest 
env:
  - MAX_BATCH_SIZE=256
  - MAX_NUM_TOKENS=16384
  - MAX_SEQ_LENGTH=16384

commands:
  - git lfs install
  - git clone https://huggingface.co/deepseek-ai/DeepSeek-R1 deepseek
  - trtllm-serve
          --backend pytorch
          --max_batch_size $MAX_BATCH_SIZE
          --max_num_tokens $MAX_NUM_TOKENS
          --max_seq_len $MAX_SEQ_LENGTH
          --tp_size $DSTACK_GPUS_NUM
          --ep_size 4
          --pp_size 1
          deepseek

port: 8000

model: deepseek-ai/DeepSeek-R1

resources:
  gpu: 8:H200
  shm_size: 32GB
  disk: 2000GB..

```
</div>
To run DeepSeek-R1-Distill-Llama-8B with TensorRT-LLM we need to build an engine and then deploy it using triton server.Here's an example of a service that deploys DeepSeek-R1-Distill-Llama-8B using TensorRT-LLM and triton server.

<div editor-title="examples/deployment/tensorrt/distill.dstack.yml">

```yaml
type: service
name: deepseek-distill

image: nvcr.io/nvidia/tritonserver:25.01-trtllm-python-py3

env:
  - HF_TOKEN
  - MODEL_REPO=https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-8B
  - MAX_SEQ_LEN=8192 # Sum of Max Input Length & Max Output Length
  - MAX_INPUT_LEN=4096 
  - MAX_BATCH_SIZE=256
  - SCRIPT_DIR=/workflow/TensorRT-LLM/examples/llama
  - CHECK_POINT_DIR=/workflow/TensorRT-LLM/examples/llama/ds-ckpt
  - ENGINE_DIR=/workflow/TensorRT-LLM/examples/llama/ds-engine
  - TOKENIZER_DIR=/workflow/TensorRT-LLM/examples/llama/DeepSeek-R1-Distill-Llama-8B
  - MODEL_FOLDER=/workflow/triton_model_repo
  - TRITON_MAX_BATCH_SIZE=1
  - INSTANCE_COUNT=1
  - MAX_QUEUE_DELAY_MS=0
  - MAX_QUEUE_SIZE=0
  - FILL_TEMPLATE_SCRIPT=/workflow/tensorrtllm_backend/tools/fill_template.py
  - DECOUPLED_MODE=true # Set true for streaming

commands:
  - cd /workflow
  # nvcr.io/nvidia/tritonserver:25.01-trtllm-python-py3 container uses TensorRT-LLM version 0.17.0,
  # therefore we are using branch v0.17.0
  - git clone --branch v0.17.0 --depth 1 https://github.com/triton-inference-server/tensorrtllm_backend.git
  - git clone --branch v0.17.0 --single-branch https://github.com/NVIDIA/TensorRT-LLM.git
  - git clone https://github.com/triton-inference-server/server.git
  - cd $SCRIPT_DIR
  - apt-get -y install git git-lfs
  - git lfs install
  - git config --global credential.helper store
  - huggingface-cli login --token $HF_TOKEN --add-to-git-credential
  - git clone $MODEL_REPO
  - python3 convert_checkpoint.py --model_dir $TOKENIZER_DIR  --output_dir $CHECK_POINT_DIR --dtype bfloat16 --tp_size $DSTACK_GPUS_NUM
  - trtllm-build --checkpoint_dir $CHECK_POINT_DIR --gemm_plugin bfloat16 --output_dir $ENGINE_DIR --max_seq_len $MAX_SEQ_LEN --max_input_len $MAX_INPUT_LEN --max_batch_size $MAX_BATCH_SIZE --gpt_attention_plugin bfloat16 --use_paged_context_fmha enable
  # Checks whether engine is working.
  - python3 ../run.py --engine_dir $ENGINE_DIR  --max_output_len 40 --tokenizer_dir $TOKENIZER_DIR  --input_text "What is Deep Learning?"
  - mkdir $MODEL_FOLDER
  - cp -r /workflow/tensorrtllm_backend/all_models/inflight_batcher_llm/* $MODEL_FOLDER/
  - python3 ${FILL_TEMPLATE_SCRIPT} -i ${MODEL_FOLDER}/ensemble/config.pbtxt triton_max_batch_size:${TRITON_MAX_BATCH_SIZE},logits_datatype:TYPE_BF16
  - python3 ${FILL_TEMPLATE_SCRIPT} -i ${MODEL_FOLDER}/preprocessing/config.pbtxt tokenizer_dir:${TOKENIZER_DIR},triton_max_batch_size:${TRITON_MAX_BATCH_SIZE},preprocessing_instance_count:${INSTANCE_COUNT}
  - python3 ${FILL_TEMPLATE_SCRIPT} -i ${MODEL_FOLDER}/tensorrt_llm/config.pbtxt triton_backend:tensorrtllm,triton_max_batch_size:${TRITON_MAX_BATCH_SIZE},decoupled_mode:${DECOUPLED_MODE},engine_dir:${ENGINE_DIR},max_queue_delay_microseconds:${MAX_QUEUE_DELAY_MS},batching_strategy:inflight_fused_batching,max_queue_size:${MAX_QUEUE_SIZE},encoder_input_features_data_type:TYPE_BF16,logits_datatype:TYPE_BF16
  - python3 ${FILL_TEMPLATE_SCRIPT} -i ${MODEL_FOLDER}/postprocessing/config.pbtxt tokenizer_dir:${TOKENIZER_DIR},triton_max_batch_size:${TRITON_MAX_BATCH_SIZE},postprocessing_instance_count:${INSTANCE_COUNT},max_queue_size:${MAX_QUEUE_SIZE}
  - python3 ${FILL_TEMPLATE_SCRIPT} -i ${MODEL_FOLDER}/tensorrt_llm_bls/config.pbtxt triton_max_batch_size:${TRITON_MAX_BATCH_SIZE},decoupled_mode:${DECOUPLED_MODE},bls_instance_count:${INSTANCE_COUNT},logits_datatype:TYPE_BF16
  - python3 /workflow/server/python/openai/openai_frontend/main.py --model-repository ${MODEL_FOLDER} --tokenizer deepseek-ai/DeepSeek-R1-Distill-Llama-8B --openai-port 8000


port: 8000

model: ensemble

resources:
  gpu: A100:40GB
```
</div>


### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command. 

<div class="termy">

```shell
$ dstack apply -f examples/deployment/tensorrt/.dstack.yml

 #  BACKEND  REGION             RESOURCES                        SPOT  PRICE       
 1  vastai   is-iceland         192xCPU, 2063GB, 8xH200 (141GB)  yes   $25.62   

Submit the run deepseek-r1? [y/n]: y

Provisioning...
---> 100%
```
</div>

If no gateway is created, the model will be available via the OpenAI-compatible endpoint 
at `<dstack server URL>/proxy/models/<project name>/`.

<div class="termy">

```shell
$ curl http://127.0.0.1:3000/proxy/models/main/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "deepseek-ai/DeepSeek-R1",
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
      "max_tokens": 128
    }'
```

</div>

When a [gateway](https://dstack.ai/docs/concepts/gateways.md) is configured, the OpenAI-compatible endpoint 
is available at `https://gateway.<gateway domain>/`.

## Source code

The source-code of this example can be found in 
[`examples/deployment/tensorrt` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/tensorrt){:target="_blank"}.

## What's next?

1. Check [services](https://dstack.ai/docs/services)
2. Browse the [Tensorrt-LLM DeepSeek-V3 Example](https://github.com/NVIDIA/TensorRT-LLM/tree/main/examples/deepseek_v3)
3. See also [Running OpenAI API compatible server with TensorRT-LLM](https://nvidia.github.io/TensorRT-LLM/commands/trtllm-serve.html#trtllm-serve)
