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
To serve DeepSeek-R1-671B, TensorRT-LLM recommends using the PyTorch backend, while DeepSeek-R1-Distill-Llama-8B requires the TensorRT-LLM backend.

The detailed process for serving both models is outlined below.

### DeepSeek-R1-671B
The latest release of TensorRT-LLM does not yet support DeepSeek-R1-671B. To serve this model, you'll need to build a Docker image from the main branch of TensorRT-LLM.

The task for building the image is defined in
[examples/deployment/trtllm/trtllm-image.dstack.yml :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/trtllm/trtllm-image.dstack.yml)

### DeepSeek-R1-Distill-Llama-8B
We have followed below steps for deployment.

1. **Convert the Hugging Face model to a TensorRT checkpoint**  
   The conversion task is defined in  
   [`examples/deployment/trtllm/convert-checkpoint.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/trtllm/convert-checkpoint.dstack.yml),  
   which also uploads the checkpoint to S3.

2. **Build the TensorRT engine and prepare the model repository**  
   This step generates the TensorRT engine from the checkpoint and creates the required model repository for Triton.  
   The corresponding task is located in  
   [`examples/deployment/trtllm/build-model.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/trtllm/build-model.dstack.yml),  
   and the output is stored in S3.

3. **Launch the Triton server with the TensorRT-LLM model**  
   The service definition for deploying the model via Triton is provided in  
   [`examples/deployment/trtllm/serve-distill.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/trtllm/serve-distill.dstack.yml).

Here are the examples of serving DeepSeek models.

=== "DeepSeek-R1-671B"
  
    <div editor-title="examples/deployment/trtllm/.dstack.yml">

    ```yaml
    type: service
    name: serve-deepseek
    # To build latest trtllm image use task in examples/deployment/trtllm/build.trtllm.yml to build docker image.
    image: dstackai/tensorrt_llm:9b931c0f6305aefa3660e6fb84a76a42c0eef167 
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

=== "DeepSeek-R1-Distill-Llama-8B"

    <div editor-title="examples/deployment/trtllm/serve-distill.dstack.yml">

    ```yaml
    type: service
    name: serve-distill-deepseek

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
   

### Running a configuration

To run a configuration to deploy DeepSeek-R1-671B, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command. 

<div class="termy">

```shell
$ dstack apply -f examples/deployment/trtllm/.dstack.yml

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
[`examples/deployment/trtllm` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/trtllm){:target="_blank"}.

## What's next?

1. Check [services](https://dstack.ai/docs/services)
2. Browse the [Tensorrt-LLM DeepSeek-V3 Example](https://github.com/NVIDIA/TensorRT-LLM/tree/main/examples/deepseek_v3), [Prepare Model Repository](https://github.com/triton-inference-server/tensorrtllm_backend?tab=readme-ov-file#prepare-the-model-repository)
3. See also [Running OpenAI API compatible server with TensorRT-LLM](https://nvidia.github.io/TensorRT-LLM/commands/trtllm-serve.html#trtllm-serve)
