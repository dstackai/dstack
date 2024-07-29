# QLORA with TPU

## Task

With the [config.yaml](config.yaml) file configured, you can run the following command to QLoRA fine-tune Gemma 2B model on tpu-v5litepod-8:

```shell
dstack run . -f examples/fine-tuning/tpu/train.dstack.yml
```

See the configuration at [train.dstack.yml](train.dstack.yml).

For more details, refer to [tasks](https://dstack.ai/docs/concepts/tasks).