# LoRaX

[LoRAX](https://github.com/predibase/lorax) allows serving multiple fine-tuned models optimized on
the same endpoint by dynamically loading and switching LoRA adapters.

## Service

The following command deploys Mistral 7B Instruct as a base model via a service:

```shell
dstack run . -f examples/deployment/lorax/serve.dstack.yml
```

See the configuration at [serve.dstack.yml](serve.dstack.yml).

## Task

The following command runs Mistral 7B Instruct as a base model via a task:

```shell
dstack run . -f examples/deployment/lorax/serve-task.dstack.yml
```

See the configuration at [serve.dstack.yml](serve-task.dstack.yml).

For more details, refer to [services](https://dstack.ai/docs/concepts/services) or [tasks](https://dstack.ai/docs/concepts/tasks).