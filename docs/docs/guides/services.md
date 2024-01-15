# Services

With `dstack`, you can use the CLI or API to deploy models or web apps.
Provide the commands, port, and choose the Python version or a Docker image.

`dstack` handles the deployment on configured cloud GPU provider(s) with the necessary resources.

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
    
    This way, if you run a service, `dstack` will make its endpoint available at 
    `https://<run-name>.example.com`.

If you're using the cloud version of `dstack`, the gateway is set up for you.

## Using the CLI

### Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `train.dstack.yml`
are both acceptable).

<div editor-title="serve.dstack.yml"> 

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

By default, `dstack` uses its own Docker images to run dev environments, 
which are pre-configured with Python, Conda, and essential CUDA drivers.

!!! info "Configuration options"
    Configuration file allows you to specify a custom Docker image, environment variables, and many other 
    options.
    For more details, refer to the [Reference](../reference/dstack.yml.md#service).

### Run the configuration

To run a configuration, use the `dstack run` command followed by the working directory path, 
configuration file path, and any other options (e.g., for requesting hardware resources).

<div class="termy">

```shell
$ dstack run . -f serve.dstack.yml --gpu A100

 BACKEND     REGION         RESOURCES                     SPOT  PRICE
 tensordock  unitedkingdom  10xCPU, 80GB, 1xA100 (80GB)   no    $1.595
 azure       westus3        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 azure       westus2        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 
Continue? [y/n]: y

Provisioning...
---> 100%

Serving HTTP on https://yellow-cat-1.example.com ...
```

</div>

Once the service is deployed, its endpoint will be available at
`https://<run-name>.<domain-name>` (using the domain [set up for the gateway](#set-up-a-gateway)).

!!! info "Run options"
    The `dstack run` command allows you to use `--gpu` to request GPUs (e.g. `--gpu A100` or `--gpu 80GB` or `--gpu A100:4`, etc.),
    and many other options (incl. spot instances, disk size, max price, max duration, retry policy, etc.).
    For more details, refer to the [Reference](../reference/cli/index.md#dstack-run).

[//]: # (TODO: Example)

### Enable OpenAI interface

To use your model via the OpenAI interface, you need to extend the configuration with `model`.

<div editor-title="mistral_openai.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:1.3

env:
  - MODEL_ID=TheBloke/Mistral-7B-OpenOrca-AWQ

port: 8000

commands:
  - text-generation-launcher --hostname 0.0.0.0 --port 8000 --quantize awq --max-input-length 3696 --max-total-tokens 4096 --max-batch-prefill-tokens 4096

model:
  type: chat
  name: TheBloke/Mistral-7B-OpenOrca-AWQ
  format: tgi
```

</div>

!!! info "Experimental feature"
    OpenAI interface is an experimental feature. 
    Only TGI chat models are supported at the moment.
    Streaming is not supported yet.

Run the configuration. Text Generation Inference requires a GPU with a compute capability above 8.0: e.g., L4 or A100.

<div class="termy">

```shell
$ dstack run . -f mistral_openai.dstack.yml --gpu L4 
```

</div>

Once the service is deployed,
OpenAI interface will be available at `https://gateway.<domain-name>` for all deployed models in the project.

The example below shows how to use the model with `openai` library:

<div editor-title="mistral_complete.py">

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://gateway.<domain-name>",
    api_key="none",
)
r = client.chat.completions.create(
    model="TheBloke/Mistral-7B-OpenOrca-AWQ",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Three main ingredients of a burger in one sentence?"}
    ],
)
print(r)
```

</div>

What's next?

1. Check the [Text Generation Inference](../../learn/tgi.md) and [vLLM](../../learn/vllm.md) examples
2. Read about [dev environments](../guides/dev-environments.md) 
    and [tasks](../guides/tasks.md)
3. Browse [examples](../../examples/index.md)
4. Check the [reference](../reference/dstack.yml.md#service)