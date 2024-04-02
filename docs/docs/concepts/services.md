# Services

Services make it very easy to deploy any kind of model or web application as public endpoints.

Use any serving frameworks and specify required resources. `dstack` deploys it in the configured backend, handles
authentication, auto-scaling, and provides an OpenAI-compatible interface if needed.

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

    In case your service has the [model mapping](#configure-model-mapping) configured, `dstack` will 
    automatically make your model available at `https://gateway.<gateway domain>` via the OpenAI-compatible interface.

    If you're using [dstack Sky](https://sky.dstack.ai), the gateway is set up for you.

## Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `train.dstack.yml`
are both acceptable).

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.1
commands:
  - text-generation-launcher --port 8000 --trust-remote-code
port: 8000

resources:
  gpu: 80GB
```

</div>

The YAML file allows you to specify your own Docker image, environment variables, 
resource requirements, etc.
If image is not specified, `dstack` uses its own (pre-configured with Python, Conda, and essential CUDA drivers).

!!! info ".dstack.yml"
    For more details on the file syntax, refer to the [`.dstack.yml` reference](../reference/dstack.yml/service.md).

### Configure environment variables

Environment variables can be set either within the configuration file or passed via the CLI.

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - HUGGING_FACE_HUB_TOKEN
  - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.1
commands:
  - text-generation-launcher --port 8000 --trust-remote-code
port: 8000

resources:
  gpu: 80GB
```

If you don't assign a value to an environment variable (see `HUGGING_FACE_HUB_TOKEN` above), 
`dstack` will require the value to be passed via the CLI or set in the current process.

For instance, you can define environment variables in a `.env` file and utilize tools like `direnv`.

### Configure model mapping

By default, if you run a service, its endpoint is accessible at `https://<run name>.<gateway domain>`.

If you run a model, you can optionally configure the mapping to make it accessible via the 
OpenAI-compatible interface.

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.1
commands:
  - text-generation-launcher --port 8000 --trust-remote-code
port: 8000
  
resources:
  gpu: 80GB
  
# Enable the OpenAI-compatible endpoint   
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

    ##### Limitations

    Please note that model mapping is an experimental feature with the following limitations:
    
    1. Doesn't work if your `chat_template` uses `bos_token`. As a workaround, replace `bos_token` inside `chat_template` with the token content itself.
    2. Doesn't work if `eos_token` is defined in the model repository as a dictionary. As a workaround, set `eos_token` manually, as shown in the example above (see Chat template).

    If you encounter any other issues, please make sure to file a [GitHub issue](https://github.com/dstackai/dstack/issues/new/choose).

### Configure replicas and auto-scaling

By default, `dstack` runs a single replica of the service.
You can configure the number of replicas as well as the auto-scaling policy.

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

python: "3.11"
env:
  - MODEL=NousResearch/Llama-2-7b-chat-hf
commands:
  - pip install vllm
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
port: 8000

replicas: 1..4
scaling:
  metric: rps
  target: 10

# Enable the OpenAI-compatible endpoint
model:
  format: openai
  type: chat
  name: NousResearch/Llama-2-7b-chat-hf
```

</div>

If you specify the minimum number of replicas as `0`, the service will scale down to zero when there are no requests.

[//]: # (??? info "Cold start")
[//]: # (    Scaling up from zero could take several minutes, considering the provisioning of a new instance and the pulling of a large model.)

## Run the configuration

To run a configuration, use the [`dstack run`](../reference/cli/index.md#dstack-run) command followed by the working directory path, 
configuration file path, and any other options.

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

When `dstack` submits the task, it uses the current folder contents.

!!! info "Exclude files"
    If there are large files or folders you'd like to avoid uploading, 
    you can list them in either `.gitignore` or `.dstackignore`.

The `dstack run` command allows specifying many things, including spot policy, retry and max duration, 
max price, regions, instance types, and [much more](../reference/cli/index.md#dstack-run).

### Service endpoint

One the service is up, its endpoint is accessible at `https://<run name>.<gateway domain>`.

#### Authentication
    
By default, the service endpoint requires the `Authentication` header with `"Bearer <dstack token>"`. 

<div class="termy">

```shell
$ curl https://yellow-cat-1.example.com/generate \
    -X POST \
    -d '{"inputs":"&lt;s&gt;[INST] What is your favourite condiment?[/INST]"}' \
    -H 'Content-Type: application/json' \
    -H 'Authentication: "Bearer &lt;dstack token&gt;"'
```

</div>

Authentication can be disabled by setting `auth` to `false` in the service configuration file.

#### OpenAI interface

In case the service has the [model mapping](#configure-model-mapping) configured, you will also be able 
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

## Configure profiles

In case you'd like to reuse certain parameters (such as spot policy, retry and max duration, 
max price, regions, instance types, etc.) across runs, you can define them via [`.dstack/profiles.yml`](../reference/profiles.yml.md).

## Manage runs

### Stop a run

When you use [`dstack stop`](../reference/cli/index.md#dstack-stop), the service and its cloud resources are deleted.

### List runs 

The [`dstack ps`](../reference/cli/index.md#dstack-ps) command lists all running runs and their status.

## What's next?

1. Check the [Text Generation Inference](../../examples/tgi.md) and [vLLM](../../examples/vllm.md) examples
2. Check the [`.dstack.yml` reference](../reference/dstack.yml/service.md) for more details and examples
3. Browse [all examples](../../examples/index.md)