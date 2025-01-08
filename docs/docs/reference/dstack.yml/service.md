# `service`

The `service` configuration type allows running [services](../../concepts/services.md).

## Root reference

#SCHEMA# dstack._internal.core.models.configurations.ServiceConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `model` { data-toc-label="model" }

=== "OpenAI"

    #SCHEMA# dstack._internal.core.models.gateways.OpenAIChatModel
        overrides:
          show_root_heading: false
          type:
            required: true

=== "TGI"

    > TGI provides an OpenAI-compatible API starting with version 1.4.0,
    so models served by TGI can be defined with `format: openai` too.
    
    #SCHEMA# dstack._internal.core.models.gateways.TGIChatModel
        overrides:
          show_root_heading: false
          type:
            required: true

    ??? info "Chat template"
    
        By default, `dstack` loads the [chat template](https://huggingface.co/docs/transformers/main/en/chat_templating)
        from the model's repository. If it is not present there, manual configuration is required.
    
        ```yaml
        type: service
    
        image: ghcr.io/huggingface/text-generation-inference:latest
        env:
          - MODEL_ID=TheBloke/Llama-2-13B-chat-GPTQ
        commands:
          - text-generation-launcher --port 8000 --trust-remote-code --quantize gptq
        port: 8000
    
        resources:
          gpu: 80GB
    
        # Enable the OpenAI-compatible endpoint
        model:
          type: chat
          name: TheBloke/Llama-2-13B-chat-GPTQ
          format: tgi
          chat_template: "{% if messages[0]['role'] == 'system' %}{% set loop_messages = messages[1:] %}{% set system_message = messages[0]['content'] %}{% else %}{% set loop_messages = messages %}{% set system_message = false %}{% endif %}{% for message in loop_messages %}{% if (message['role'] == 'user') != (loop.index0 % 2 == 0) %}{{ raise_exception('Conversation roles must alternate user/assistant/user/assistant/...') }}{% endif %}{% if loop.index0 == 0 and system_message != false %}{% set content = '<<SYS>>\\n' + system_message + '\\n<</SYS>>\\n\\n' + message['content'] %}{% else %}{% set content = message['content'] %}{% endif %}{% if message['role'] == 'user' %}{{ '<s>[INST] ' + content.strip() + ' [/INST]' }}{% elif message['role'] == 'assistant' %}{{ ' '  + content.strip() + ' </s>' }}{% endif %}{% endfor %}"
          eos_token: "</s>"
        ```
    
        Please note that model mapping is an experimental feature with the following limitations:
    
        1. Doesn't work if your `chat_template` uses `bos_token`. As a workaround, replace `bos_token` inside `chat_template` with the token content itself.
        2. Doesn't work if `eos_token` is defined in the model repository as a dictionary. As a workaround, set `eos_token` manually, as shown in the example above (see Chat template).
    
        If you encounter any other issues, please make sure to file a 
        [GitHub issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/new/choose){:target="_blank"}.

### `scaling`

#SCHEMA# dstack._internal.core.models.configurations.ScalingSpec
    overrides:
      show_root_heading: false
      type:
        required: true

### `retry`

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetry
    overrides:
      show_root_heading: false

### `resources`

#SCHEMA# dstack._internal.core.models.resources.ResourcesSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true
      item_id_prefix: resources-

#### `resouces.gpu` { #resources-gpu data-toc-label="gpu" }

#SCHEMA# dstack._internal.core.models.resources.GPUSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

#### `resouces.disk` { #resources-disk data-toc-label="disk" }

#SCHEMA# dstack._internal.core.models.resources.DiskSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

### `registry_auth`

#SCHEMA# dstack._internal.core.models.configurations.RegistryAuth
    overrides:
      show_root_heading: false
      type:
        required: true

### `volumes[n]` { #_volumes data-toc-label="volumes" }

=== "Network volumes"

    #SCHEMA# dstack._internal.core.models.volumes.VolumeMountPoint
        overrides:
          show_root_heading: false
          type:
            required: true

=== "Instance volumes"

    #SCHEMA# dstack._internal.core.models.volumes.InstanceMountPoint
        overrides:
          show_root_heading: false
          type:
            required: true

??? info "Short syntax"

    The short syntax for volumes is a colon-separated string in the form of `source:destination`

    * `volume-name:/container/path` for network volumes
    * `/instance/path:/container/path` for instance volumes
