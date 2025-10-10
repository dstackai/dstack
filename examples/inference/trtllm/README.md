---
title: TensorRT-LLM
description: "This example shows how to deploy Deepseek models to any cloud or on-premises environment using NVIDIA TensorRT-LLM and dstack."
---

# TensorRT-LLM

This example shows how to deploy both DeepSeek R1 and its distilled version
using [TensorRT-LLM :material-arrow-top-right-thin:{ .external }](https://github.com/NVIDIA/TensorRT-LLM){:target="_blank"} and `dstack`.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo with examples.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    ```
 
    </div>

## Deployment

### DeepSeek R1

We normally use Triton with the TensorRT-LLM backend to serve models. While this works for the distilled Llama-based
version, DeepSeek R1 isn’t yet compatible. So, for DeepSeek R1, we’ll use `trtllm-serve` with the PyTorch backend instead.

To use `trtllm-serve`, we first need to build the TensorRT-LLM Docker image from the `main` branch.

#### Build a Docker image

Here’s the task config that builds the image and pushes it using the provided Docker credentials.

<div editor-title="examples/inference/trtllm/build-image.dstack.yml">

```yaml
type: task
name: build-image

privileged: true
image: dstackai/dind
env:
  - DOCKER_USERNAME
  - DOCKER_PASSWORD
commands:
  - start-dockerd
  - apt update && apt-get install -y build-essential make git git-lfs
  - git lfs install
  - git clone https://github.com/NVIDIA/TensorRT-LLM.git
  - cd TensorRT-LLM
  - git submodule update --init --recursive
  - git lfs pull
  # Limit compilation to Hopper for a smaller image
  - make -C docker release_build CUDA_ARCHS="90-real"
  - docker tag tensorrt_llm/release:latest $DOCKER_USERNAME/tensorrt_llm:latest
  - echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin
  - docker push "$DOCKER_USERNAME/tensorrt_llm:latest"

resources:
  cpu: 8
  disk: 500GB..
```
</div>

To run it, pass the task configuration to `dstack apply`.

<div class="termy">

```shell
$ dstack apply -f examples/inference/trtllm/build-image.dstack.yml

 #  BACKEND  REGION             RESOURCES               SPOT  PRICE
 1  cudo     ca-montreal-2      8xCPU, 25GB, (500.0GB)  yes   $0.1073

Submit the run build-image? [y/n]: y

Provisioning...
---> 100%
```
</div>

#### Deploy the model

Below is the service configuration that deploys DeepSeek R1 using the built TensorRT-LLM image.

<div editor-title="examples/inference/trtllm/serve-r1.dstack.yml">

    ```yaml
    type: service
    name: serve-r1

    # Specify the image built with `examples/inference/trtllm/build-image.dstack.yml`
    image: dstackai/tensorrt_llm:9b931c0f6305aefa3660e6fb84a76a42c0eef167
    env:
      - MAX_BATCH_SIZE=256
      - MAX_NUM_TOKENS=16384
      - MAX_SEQ_LENGTH=16384
      - EXPERT_PARALLEL=4
      - PIPELINE_PARALLEL=1
      - HF_HUB_ENABLE_HF_TRANSFER=1
    commands:
      - pip install -U "huggingface_hub[cli]"
      - pip install hf_transfer
      - huggingface-cli download deepseek-ai/DeepSeek-R1 --local-dir DeepSeek-R1
      - trtllm-serve
              --backend pytorch
              --max_batch_size $MAX_BATCH_SIZE
              --max_num_tokens $MAX_NUM_TOKENS
              --max_seq_len $MAX_SEQ_LENGTH
              --tp_size $DSTACK_GPUS_NUM
              --ep_size $EXPERT_PARALLEL
              --pp_size $PIPELINE_PARALLEL
              DeepSeek-R1
    port: 8000
    model: deepseek-ai/DeepSeek-R1

    resources:
      gpu: 8:H200
      shm_size: 32GB
      disk: 2000GB..
    ```
    </div>


To run it, pass the configuration to `dstack apply`.

<div class="termy">

```shell
$ dstack apply -f examples/inference/trtllm/serve-r1.dstack.yml

 #  BACKEND  REGION             RESOURCES                        SPOT  PRICE
 1  vastai   is-iceland         192xCPU, 2063GB, 8xH200 (141GB)  yes   $25.62

Submit the run serve-r1? [y/n]: y

Provisioning...
---> 100%
```
</div>


### DeepSeek R1 Distill Llama 8B

To deploy DeepSeek R1 Distill Llama 8B, follow the steps below.

#### Convert and upload checkpoints

Here’s the task config that converts a Hugging Face model to a TensorRT-LLM checkpoint format
and uploads it to S3 using the provided AWS credentials.

<div editor-title="examples/inference/trtllm/convert-model.dstack.yml">

    ```yaml
    type: task
    name: convert-model

    image: nvcr.io/nvidia/tritonserver:25.01-trtllm-python-py3
    env:
      - HF_TOKEN
      - MODEL_REPO=https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-8B
      - S3_BUCKET_NAME
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
      - AWS_DEFAULT_REGION
    commands:
      # nvcr.io/nvidia/tritonserver:25.01-trtllm-python-py3 container uses TensorRT-LLM version 0.17.0,
      # therefore we are using branch v0.17.0
      - git clone --branch v0.17.0 --depth 1 https://github.com/triton-inference-server/tensorrtllm_backend.git
      - git clone --branch v0.17.0 --single-branch https://github.com/NVIDIA/TensorRT-LLM.git
      - git clone https://github.com/triton-inference-server/server.git
      - cd TensorRT-LLM/examples/llama
      - apt-get -y install git git-lfs
      - git lfs install
      - git config --global credential.helper store
      - huggingface-cli login --token $HF_TOKEN --add-to-git-credential
      - git clone $MODEL_REPO
      - python3 convert_checkpoint.py --model_dir DeepSeek-R1-Distill-Llama-8B  --output_dir tllm_checkpoint_${DSTACK_GPUS_NUM}gpu_bf16 --dtype bfloat16 --tp_size $DSTACK_GPUS_NUM
      # Download the AWS CLI
      - curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
      - unzip awscliv2.zip
      - ./aws/install
      - aws s3 sync tllm_checkpoint_${DSTACK_GPUS_NUM}gpu_bf16 s3://${S3_BUCKET_NAME}/tllm_checkpoint_${DSTACK_GPUS_NUM}gpu_bf16 --acl public-read

    resources:
      gpu: A100:40GB

    ```
    </div>


To run it, pass the configuration to `dstack apply`.

<div class="termy">

```shell
$ dstack apply -f examples/inference/trtllm/convert-model.dstack.yml

 #  BACKEND  REGION       RESOURCES                    SPOT  PRICE
 1  vastai   us-iowa      12xCPU, 85GB, 1xA100 (40GB)  yes   $0.66904

Submit the run convert-model? [y/n]: y

Provisioning...
---> 100%
```
</div>


#### Build and upload the model

Here’s the task config that builds a TensorRT-LLM model and uploads it to S3 with the provided AWS credentials.

<div editor-title="build-model.dstack.yml">

    ```yaml
      type: task
      name: build-model

      image: nvcr.io/nvidia/tritonserver:25.01-trtllm-python-py3
      env:
        - MODEL=deepseek-ai/DeepSeek-R1-Distill-Llama-8B
        - S3_BUCKET_NAME
        - AWS_ACCESS_KEY_ID
        - AWS_SECRET_ACCESS_KEY
        - AWS_DEFAULT_REGION
        - MAX_SEQ_LEN=8192 # Sum of Max Input Length & Max Output Length
        - MAX_INPUT_LEN=4096
        - MAX_BATCH_SIZE=256
        - TRITON_MAX_BATCH_SIZE=1
        - INSTANCE_COUNT=1
        - MAX_QUEUE_DELAY_MS=0
        - MAX_QUEUE_SIZE=0
        - DECOUPLED_MODE=true # Set true for streaming
      commands:
        - huggingface-cli download $MODEL --exclude '*.safetensors' --local-dir tokenizer_dir
        - curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
        - unzip awscliv2.zip
        - ./aws/install
        - aws s3 sync s3://${S3_BUCKET_NAME}/tllm_checkpoint_${DSTACK_GPUS_NUM}gpu_bf16 ./tllm_checkpoint_${DSTACK_GPUS_NUM}gpu_bf16
        - trtllm-build --checkpoint_dir tllm_checkpoint_${DSTACK_GPUS_NUM}gpu_bf16 --gemm_plugin bfloat16 --output_dir tllm_engine_${DSTACK_GPUS_NUM}gpu_bf16  --max_seq_len $MAX_SEQ_LEN --max_input_len $MAX_INPUT_LEN --max_batch_size $MAX_BATCH_SIZE --gpt_attention_plugin bfloat16 --use_paged_context_fmha enable
        - git clone --branch v0.17.0 --single-branch https://github.com/NVIDIA/TensorRT-LLM.git
        - python3 TensorRT-LLM/examples/run.py --engine_dir tllm_engine_${DSTACK_GPUS_NUM}gpu_bf16 --max_output_len 40 --tokenizer_dir tokenizer_dir  --input_text "What is Deep Learning?"
        - git clone --branch v0.17.0 --depth 1 https://github.com/triton-inference-server/tensorrtllm_backend.git
        - mkdir triton_model_repo
        - cp -r tensorrtllm_backend/all_models/inflight_batcher_llm/* triton_model_repo/
        - python3 tensorrtllm_backend/tools/fill_template.py -i triton_model_repo/ensemble/config.pbtxt triton_max_batch_size:${TRITON_MAX_BATCH_SIZE},logits_datatype:TYPE_BF16
        - python3 tensorrtllm_backend/tools/fill_template.py -i triton_model_repo/preprocessing/config.pbtxt tokenizer_dir:tokenizer_dir,triton_max_batch_size:${TRITON_MAX_BATCH_SIZE},preprocessing_instance_count:${INSTANCE_COUNT}
        - python3 tensorrtllm_backend/tools/fill_template.py -i triton_model_repo/tensorrt_llm/config.pbtxt triton_backend:tensorrtllm,triton_max_batch_size:${TRITON_MAX_BATCH_SIZE},decoupled_mode:${DECOUPLED_MODE},engine_dir:tllm_engine_${DSTACK_GPUS_NUM}gpu_bf16,max_queue_delay_microseconds:${MAX_QUEUE_DELAY_MS},batching_strategy:inflight_fused_batching,max_queue_size:${MAX_QUEUE_SIZE},encoder_input_features_data_type:TYPE_BF16,logits_datatype:TYPE_BF16
        - python3 tensorrtllm_backend/tools/fill_template.py -i triton_model_repo/postprocessing/config.pbtxt tokenizer_dir:tokenizer_dir,triton_max_batch_size:${TRITON_MAX_BATCH_SIZE},postprocessing_instance_count:${INSTANCE_COUNT},max_queue_size:${MAX_QUEUE_SIZE}
        - python3 tensorrtllm_backend/tools/fill_template.py -i triton_model_repo/tensorrt_llm_bls/config.pbtxt triton_max_batch_size:${TRITON_MAX_BATCH_SIZE},decoupled_mode:${DECOUPLED_MODE},bls_instance_count:${INSTANCE_COUNT},logits_datatype:TYPE_BF16
        - aws s3 sync triton_model_repo s3://${S3_BUCKET_NAME}/triton_model_repo --acl public-read
        - aws s3 sync tllm_engine_${DSTACK_GPUS_NUM}gpu_bf16 s3://${S3_BUCKET_NAME}/tllm_engine_${DSTACK_GPUS_NUM}gpu_bf16 --acl public-read

      resources:
        gpu: A100:40GB
    ```
    </div>

To run it, pass the configuration to `dstack apply`.

<div class="termy">

```shell
$ dstack apply -f examples/inference/trtllm/build-model.dstack.yml

 #  BACKEND  REGION       RESOURCES                    SPOT  PRICE
 1  vastai   us-iowa      12xCPU, 85GB, 1xA100 (40GB)  yes   $0.66904

Submit the run build-model? [y/n]: y

Provisioning...
---> 100%
```
</div>

#### Deploy the model

Below is the service configuration that deploys DeepSeek R1 Distill Llama 8B.

<div editor-title="serve-distill.dstack.yml">

```yaml
    type: service
    name: serve-distill

    image: nvcr.io/nvidia/tritonserver:25.01-trtllm-python-py3
    env:
      - MODEL=deepseek-ai/DeepSeek-R1-Distill-Llama-8B
      - S3_BUCKET_NAME
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
      - AWS_DEFAULT_REGION

    commands:
      - huggingface-cli download $MODEL --exclude '*.safetensors' --local-dir tokenizer_dir
      - curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
      - unzip awscliv2.zip
      - ./aws/install
      - aws s3 sync s3://${S3_BUCKET_NAME}/tllm_engine_1gpu_bf16 ./tllm_engine_1gpu_bf16
      - git clone https://github.com/triton-inference-server/server.git
      - python3 server/python/openai/openai_frontend/main.py --model-repository s3://${S3_BUCKET_NAME}/triton_model_repo  --tokenizer tokenizer_dir --openai-port 8000
    port: 8000
    model: ensemble

    resources:
      gpu: A100:40GB

```
</div>

To run it, pass the configuration to `dstack apply`.

<div class="termy">

```shell
$ dstack apply -f examples/inference/trtllm/serve-distill.dstack.yml

 #  BACKEND  REGION       RESOURCES                    SPOT  PRICE
 1  vastai   us-iowa      12xCPU, 85GB, 1xA100 (40GB)  yes   $0.66904

Submit the run serve-distill? [y/n]: y

Provisioning...
---> 100%
```
</div>

## Access the endpoint

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

When a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured, the OpenAI-compatible endpoint
is available at `https://gateway.<gateway domain>/`.

## Source code

The source-code of this example can be found in
[`examples/inference/trtllm` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/inference/trtllm){:target="_blank"}.

## What's next?

1. Check [services](https://dstack.ai/docs/services)
2. Browse [Tensorrt-LLM DeepSeek-R1 with PyTorch Backend :material-arrow-top-right-thin:{ .external }](https://github.com/NVIDIA/TensorRT-LLM/tree/main/examples/deepseek_v3){:target="_blank"} and [Prepare the Model Repository :material-arrow-top-right-thin:{ .external }](https://github.com/triton-inference-server/tensorrtllm_backend?tab=readme-ov-file#prepare-the-model-repository){:target="_blank"}
3. See also [`trtllm-serve` :material-arrow-top-right-thin:{ .external }](https://nvidia.github.io/TensorRT-LLM/commands/trtllm-serve.html#trtllm-serve){:target="_blank"}
