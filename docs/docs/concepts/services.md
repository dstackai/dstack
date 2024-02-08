# Services

Services make it easy to deploy models and apps as public endpoints, while giving you the flexibility to use any
frameworks.

??? info "Prerequisites"

    If you're using the open-source server, you first have to set up a gateway.

    ### Set up a gateway

    For example, if your domain is `example.com`, go ahead and run the 
    `dstack gateway create` command:
    
    <div class="termy">
       
    ```shell
    $ dstack gateway create --domain example.com --region eu-west-1 --backend aws
    
    Creating gateway...
    ---> 100%
    
     BACKEND  REGION     NAME          ADDRESS        DOMAIN       DEFAULT
     aws      eu-west-1  sour-fireant  52.148.254.14  example.com  ✓
    ```
    
    </div>
    
    Afterward, in your domain's DNS settings, add an `A` DNS record for `*.example.com` 
    pointing to the IP address of the gateway.
    
    Now, if you run a service, `dstack` will make its endpoint available at 
    `https://<run name>.<gateway domain>`.

    In case your service has the [model mapping](#model-mapping) configured, `dstack` will 
    automatically make your model available at `https://gateway.<gateway domain>` via the OpenAI-compatible interface.

If you're using the cloud version of `dstack`, the gateway is set up for you.

## Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `train.dstack.yml`
are both acceptable).

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.1
port: 80
commands:
  - text-generation-launcher --port 80 --trust-remote-code

# (Optional) Configure `gpu`, `memory`, `disk`, etc
resources:
  gpu: 80GB
```

</div>

The `image` property is optional. If not specified, `dstack` uses its own Docker image, 
pre-configured with Python, Conda, and essential CUDA drivers.

If you run such a configuration, once the service is up, you'll be able to 
access it at `https://<run name>.<gateway domain>` (see how to [set up a gateway](#set-up-a-gateway)).

!!! info "Configuration options"
    Configuration file allows you to specify a custom Docker image, environment variables, and many other
    options. For more details, refer to the [Reference](../reference/dstack.yml.md#service).

### Model mapping

If your service is running a model, you can configure the model mapping to be able to access it via the
OpenAI-compatible interface.

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.1
port: 80
commands:
  - text-generation-launcher --port 80 --trust-remote-code
  
# (Optional) Configure `gpu`, `memory`, `disk`, etc
resources:
  gpu: 80GB
  
# (Optional) Enable the OpenAI-compatible endpoint   
model:
  type: chat
  name: mistralai/Mistral-7B-Instruct-v0.1
  format: tgi
```

</div>

In this case, with such a configuration, once the service is up, you'll be able to access the model at
`https://gateway.<gateway domain>` via the OpenAI-compatible interface.

The `format` supports only `tgi` (Text Generation Inference) 
and `openai` (if you are using Text Generation Inference or vLLM with OpenAI-compatible mode).

##### Chat template

By default, `dstack` loads the [chat template](https://huggingface.co/docs/transformers/main/en/chat_templating) 
from the model's repository. If it is not present there, manual configuration is required.

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - MODEL_ID=TheBloke/Llama-2-13B-chat-GPTQ
port: 80
commands:
  - text-generation-launcher --port 80 --trust-remote-code --quantize gptq

# (Optional) Configure `gpu`, `memory`, `disk`, etc
resources:
  gpu: 80GB
  
# (Optional) Enable the OpenAI-compatible endpoint
model:
  type: chat
  name: TheBloke/Llama-2-13B-chat-GPTQ
  format: tgi
  chat_template: "{% if messages[0]['role'] == 'system' %}{% set loop_messages = messages[1:] %}{% set system_message = messages[0]['content'] %}{% else %}{% set loop_messages = messages %}{% set system_message = false %}{% endif %}{% for message in loop_messages %}{% if (message['role'] == 'user') != (loop.index0 % 2 == 0) %}{{ raise_exception('Conversation roles must alternate user/assistant/user/assistant/...') }}{% endif %}{% if loop.index0 == 0 and system_message != false %}{% set content = '<<SYS>>\\n' + system_message + '\\n<</SYS>>\\n\\n' + message['content'] %}{% else %}{% set content = message['content'] %}{% endif %}{% if message['role'] == 'user' %}{{ '<s>[INST] ' + content.strip() + ' [/INST]' }}{% elif message['role'] == 'assistant' %}{{ ' '  + content.strip() + ' </s>' }}{% endif %}{% endfor %}"
  eos_token: "</s>"
```

??? info "Limitations"
    Note that model mapping is an experimental feature, and it has the following limitations:
    
    1. Doesn't work if your `chat_template` uses `bos_token`. As a workaround, replace `bos_token` inside `chat_template` with the token content itself.
    2. Doesn't work if `eos_token` is defined in the model repository as a dictionary. As a workaround, set `eos_token` manually, as shown in the example above (see Chat template).

    If you encounter any other issues, please make sure to file a [GitHub issue](https://github.com/dstackai/dstack/issues/new/choose).

## Run the configuration

To run a configuration, use the `dstack run` command followed by the working directory path, 
configuration file path, and any other options (e.g., for requesting hardware resources).

<div class="termy">

```shell
$ dstack run . -f serve.dstack.yml

 BACKEND     REGION         RESOURCES                     SPOT  PRICE
 tensordock  unitedkingdom  10xCPU, 80GB, 1xA100 (80GB)   no    $1.595
 azure       westus3        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 azure       westus2        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 
Continue? [y/n]: y

Provisioning...
---> 100%

Service is published at https://yellow-cat-1.example.com
```

</div>

!!! info "Run options"
    The `dstack run` command allows you to use specify the spot policy (e.g. `--spot-auto`, `--spot`, or `--on-demand`), 
    max duration of the run (e.g. `--max-duration 1h`), and many other options.
    For more details, refer to the [Reference](../reference/cli/index.md#dstack-run).

### Service endpoint

Once the service is up, you'll be able to access it at `https://<run name>.<gateway domain>`.

#### Authentication
    
By default, the service endpoint requires the `Authentication` header with `"Bearer <dstack token>"`. 
Authentication can be disabled by setting `auth` to `false` in the service configuration file.

<div class="termy">

```shell
$ curl https://yellow-cat-1.example.com/generate \
    -X POST \
    -d '{"inputs":"&lt;s&gt;[INST] What is your favourite condiment?[/INST]"}' \
    -H 'Content-Type: application/json' \
    -H 'Authentication: "Bearer &lt;dstack token&gt;"'
```

</div>

#### OpenAI interface

In case the service has the [model mapping](#model-mapping) configured, you will also be able 
to access the model at `https://gateway.<gateway domain>` via the OpenAI-compatible interface.

```python
from openai import OpenAI


client = OpenAI(
  base_url="https://gateway.example.com",
  api_key="<dstack token>"
)

completion = client.chat.completions.create(
  model="mistralai/Mistral-7B-Instruct-v0.1",
  messages=[
    {"role": "user", "content": "Compose a poem that explains the concept of recursion in programming."}
  ]
)

print(completion.choices[0].message)
```

## What's next?

1. Check the [Text Generation Inference](../../examples/tgi.md) and [vLLM](../../examples/vllm.md) examples
2. Read about [dev environments](../concepts/dev-environments.md) 
    and [tasks](../concepts/tasks.md)
3. Browse [examples](../../examples/index.md)
4. Check the [reference](../reference/dstack.yml.md#service)