# Services

Services make it very easy to deploy any kind of model or application as public,
secure, and scalable endpoints.

??? info "Gateway"

    If you're using the open-source server, you first have to set up a gateway.

    ### Gateway { style="display:none" }

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

    If you're using [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}, the gateway is set up for you.

## Configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `serve.dstack.yml`
are both acceptable).

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

resources:
  gpu: 80GB

# (Optional) Enable the OpenAI-compatible endpoint
model:
  format: openai
  type: chat
  name: NousResearch/Llama-2-7b-chat-hf
```

</div>

If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
(pre-configured with Python, Conda, and essential CUDA drivers).

By default, the service is deployed to a single instance. However, you can specify the
[number of replicas and scaling policy](../reference/dstack.yml/service.md#replicas-and-auto-scaling), so `dstack`
auto-scales it based on the load.

> See the [.dstack.yml reference](../reference/dstack.yml/service.md)
> for many examples on service configuration.

## Running

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

When deploying the service, `dstack run` mounts the current folder's contents.

!!! info ".gitignore"
    If there are large files or folders you'd like to avoid uploading, 
    you can list them in `.gitignore`.

> See the [CLI reference](../reference/cli/index.md#dstack-run) for more details
> on how `dstack run` works.

## Service endpoint

One the service is up, its endpoint is accessible at `https://<run name>.<gateway domain>`.

By default, the service endpoint requires the `Authorization` header with `"Bearer <dstack token>"`. 

<div class="termy">

```shell
$ curl https://yellow-cat-1.example.com/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -H 'Authorization: "Bearer &lt;dstack token&gt;"' \
    -d '{
        "model": "NousResearch/Llama-2-7b-chat-hf",
        "messages": [
            {
                "role": "user",
                "content": "Compose a poem that explains the concept of recursion in programming."
            }
        ]
    }'
```

</div>

Authorization can be disabled by setting `auth` to `false` in the service configuration file.

### Model endpoint

In case the service has the [model mapping](../reference/dstack.yml/service.md#model-mapping) configured, you will also be able
to access the model at `https://gateway.<gateway domain>` via the OpenAI-compatible interface.

## Managing runs

**Stopping runs**

When you use [`dstack stop`](../reference/cli/index.md#dstack-stop), the service and its cloud resources are deleted.

**Listing runs**

The [`dstack ps`](../reference/cli/index.md#dstack-ps) command lists all running runs and their status.

## What's next?

1. Check the [Text Generation Inference :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/tgi/README.md){:target="_blank"} and [vLLM :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/vllm/README.md){:target="_blank"} examples
2. Check the [`.dstack.yml` reference](../reference/dstack.yml/service.md) for more details and examples
3. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}