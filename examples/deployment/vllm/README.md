# vLLM
This example shows how to use [vLLM :material-arrow-top-right-thin:{ .external }](https://github.com/vllm-project/vllm){:target="_blank"} 
with `dstack` to fine-tune Llama3 8B using FSDP and QLoRA.
## Service

The following command deploys Llama 7B Instruct as a service:

```shell
dstack run . -f examples/deployment/vllm/serve.dstack.yml
```

See the configuration at [`serve.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/vllm/serve.dstack.yml).

## Task

The following command runs Llama 7B Instruct as a task:

```shell
dstack run . -f examples/deployment/vllm/serve-task.dstack.yml
```

See the configuration at [`serve-task.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/vllm/serve-task.dstack.yml).

For more details, refer to [services](https://dstack.ai/docs/services) or [tasks](https://dstack.ai/docs/tasks).