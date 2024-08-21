# TPU

Examples below show how to deploy and fine-tune LLM models on TPU [v5e](https://cloud.google.com/tpu/docs/v5e) using [Hugging Face Optimum TPU](https://github.com/huggingface/optimum-tpu) with `dstack`. 


## Deployment

### Running as a task

If you'd like to run Llama 3.1-8B for development purposes, consider using `dstack` tasks. 
Here, we use `optimum-tpu`, which utilizes the `TGI` framework to serve the model. 

=== "optimum-tpu"

    <div editor-title="examples/deployment/optimum-tpu/task.dstack.yml"> 

    ```yaml
      type: task
      name: tpu-task
      # This task runs Meta-Llama-3.1-8B with TGI
      # Refer to Note section in README.md for more information about the image.
      image: sjbbihan/optimum-tpu:latest
      env:
        - HUGGING_FACE_HUB_TOKEN
        - MODEL_ID=meta-llama/Meta-Llama-3.1-8B
      commands:
        - text-generation-launcher --port 8000 --max-concurrent-requests 4 --max-input-tokens 128 --max-total-tokens 150 --max-batch-prefill-tokens 128
      ports:
        - 8000

      resources:
        gpu: v5litepod-8
    ```
    </div>

**Note:** The official Docker image `huggingface/optimum-tpu:latest` currently does not support the deploying Llama 3.1-8B. 
To address this, we have forked the optimum-tpu repository and built a custom Docker image `sjbbihan/optimum-tpu:latest` that includes the necessary updates 
for Llama 3.1-8B deployment. We have raised a [pull request](https://github.com/huggingface/optimum-tpu/pull/85) to officially incorporate these changes. 
Once it is merged, the official Docker image will be updated accordingly.

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/index.md#dstack-apply) command.

<div class="termy">

```shell
$ HUGGING_FACE_HUB_TOKEN=...

$ dstack apply -f examples/deployment/optimum-tpu/task.dstack.yml

#  BACKEND  REGION       INSTANCE     RESOURCES                      SPOT  PRICE   
 1  gcp      us-central1  v5litepod-8  1xv5litepod-8, 100.0GB (disk)  yes   $4.8    
 2  gcp      us-east5     v5litepod-8  1xv5litepod-8, 100.0GB (disk)  yes   $4.8    
 3  gcp      us-south1    v5litepod-8  1xv5litepod-8, 100.0GB (disk)  yes   $4.8    
    ...                                                                             
 Shown 3 of 12 offers, $12.48 max

Submit the run llama31-task-optimum-tpu? [y/n]: 

Provisioning...
---> 100%
```

</div>

If you run a task, `dstack apply` automatically forwards the remote ports to `localhost` for convenient access.

<div class="termy">

```shell
$ curl localhost:8000/generate \
    -X POST \
    -d '{"inputs":"What is Deep Learning?","parameters":{"max_new_tokens":20}}' \
    -H 'Content-Type: application/json'
```

</div>


### Deploying as a service

If you'd like to deploy Llama 3.1-8B as public auto-scalable and secure endpoint,
consider using `dstack` [services](https://dstack.ai/docs/services).


## Fine-Tuning

Below is an example of fine-tuning Llama 3.1-8B on the
[English Quotes Dataset](https://huggingface.co/datasets/Abirate/english_quotes):

<div editor-title="examples/fine-tuning/optimum-tpu/llama31/train.dstack.yml"> 

```yaml
type: task
name: optimum-tpu-llama-train

python: "3.11"

env:
  - HUGGING_FACE_HUB_TOKEN

# Refer to Note section in README.md for more information about the optimum-tpu repository.
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
 

### Fine-Tuning with TRL

Use the example `examples/fine-tuning/optimum-tpu/gemma/train.dstack.yml` to Finetune `Gemma-2B` model using `trl` with `dstack` and `optimum-tpu`. 

## Dev environments

Before running a task or service, it's recommended that you first start with
a [dev environment](https://dstack.ai/docs/dev-environments). Dev environments
allow you to run commands interactively.

## Source code

The source-code of this example can be found in 
[examples/deployment/optimum-tpu](https://github.com/dstackai/dstack/blob/master/examples/llms/llama31)
and [examples/fine-tuning/optimum-tpu](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/trl).

## Contributing

Find a mistake or can't find an important example? 
Raise an [issue](https://github.com/dstackai/dstack/issues) or send a [pull request](https://github.com/dstackai/dstack/tree/master/examples).

## What's next?

1. Browse [Optimum-TPU :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu/tree/main),
   [Optimum-TPU Text Generation Inference :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-tpu/tree/main/text-generation-inference).
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/fleets).
