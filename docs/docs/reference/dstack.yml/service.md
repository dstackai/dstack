# .dstack.yml (service)

A service is a web app accessible from the Internet.

The configuration file name must end with `.dstack.yml` (e.g., `.dstack.yml` or `service.dstack.yml` are both acceptable).

## Example

<div editor-title="service.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest

env: 
  - MODEL_ID=TheBloke/Llama-2-13B-chat-GPTQ 

port: 80

commands:
  - text-generation-launcher --hostname 0.0.0.0 --port 80 --trust-remote-code
```

</div>

## YAML reference

#SCHEMA# dstack._internal.core.models.configurations.ServiceConfiguration
    overrides:
      type:
        required: true
