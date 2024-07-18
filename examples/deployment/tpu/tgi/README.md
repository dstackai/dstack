# Text Generation Inference

## Service

The following command deploys Mistral 7B Instruct as a service:

```shell
dstack run . -f examples/deployment/tpu/tgi/serve.dstack.yml
```

See the configuration at [serve.dstack.yml](serve.dstack.yml).

## Task

The following command runs Mistral 7B Instruct as a task:

```shell
dstack run . -f examples/deployment/tpu/tgi/serve-task.dstack.yml
```

See the configuration at [serve.dstack.yml](serve-task.dstack.yml).

For more details, refer to [services](https://dstack.ai/docs/concepts/services) or [tasks](https://dstack.ai/docs/concepts/tasks).

## Text Generation Launcher Arguments

```shell
--max-concurrent-requests #concurrent clients requests 
--max-input-tokens # maximum allowed input length
--max-total-tokens # should be equal to max-input-token + max_new_tokens
--max-batch-prefill-tokens # limits the number of tokens for the prefill operation and should be equal to --max-input-tokens
```

See [CLI reference](https://huggingface.co/docs/text-generation-inference/en/basic_tutorials/launcher) for more details.

We have used the Docker image from Hugging Face Optimum-tpu (huggingface/optimum-tpu
) which includes specialized tools and integrations for harnessing Cloud TPUs, particularly for inference tasks on the 
latest version `v5litepod`. Optimum-tpu effectively employs all `TPU Cores` during inference.

Currently, they support few LLM models:

- Gemma (2b, 7b)
- Llama2 (7b) and Llama3 (8b)
- Mistral (7b)

For more information check their official [repo](https://github.com/huggingface/optimum-tpu)