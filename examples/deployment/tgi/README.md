# Text Generation Inference

## Service

The following command deploys Llama 7B Instruct as a service:

```shell
dstack run . -f examples/deployment/tgi/serve.dstack.yml
```

See the configuration at [serve.dstack.yml](serve.dstack.yml).

## Task

The following command runs Llama 7B Instruct as a task:

```shell
dstack run . -f examples/deployment/tgi/serve-task.dstack.yml
```

See the configuration at [serve.dstack.yml](serve-task.dstack.yml).

For more details, refer to [services](https://dstack.ai/docs/services) or [tasks](https://dstack.ai/docs/tasks).