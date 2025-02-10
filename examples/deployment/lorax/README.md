# LoRaX

[LoRAX](https://github.com/predibase/lorax) allows serving multiple fine-tuned models optimized on
the same endpoint by dynamically loading and switching LoRA adapters.

The following command deploys Mistral 7B Instruct as a base model via a service:

```shell
dstack apply -f examples/deployment/lorax/.dstack.yml
```

See the configuration at [.dstack.yml](.dstack.yml).

For more details, refer to [services](https://dstack.ai/docs/services).
