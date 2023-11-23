# Text generation

The easiest way to deploy a text generation model is by using `dstack` API.
You only need to specify a model, quantization parameters, 
and required compute resources.

??? info "Prerequisites"
    If you're using the cloud version of `dstack`, no prerequisites are required.

    However, if you're using the open-source server, you need to 
    [set up a gateway](services.md#set-up-a-gateway) before running models as public endpoints. 
    Not required for private endpoints.

## Create a client

First, you connect to `dstack`:

```python
from dstack.api import Client, ClientError

try:
    client = Client.from_config()
except ClientError:
    print("Can't connect to the server")
```

## Create a configuration

`dstack` allows to run a model either as a public endpoint or as a private endpoint.

=== "Public endpoint"

    ```python
    from dstack.api import CompletionService
    
    configuration = CompletionService(
        model_name="TheBloke/CodeLlama-34B-GPTQ",
        quantize="gptq"
    )
    ```

    > When you run a model as a public endpoint, `dstack` makes it available
    at `https://<run-name>.<domain-name>` (using the domain set up for the gateway).

=== "Private endpoint"

    ```python
    from dstack.api import CompletionTask
    
    configuration = CompletionTask(
        model_name="TheBloke/CodeLlama-34B-GPTQ",
        quantize="gptq",
        local_port="8080,
    )
    ```
    
    > When you run a model as a private endpoint, `dstack` makes it available
    only at `http://localhost:<local_port>` (even though the model itself is running in the cloud). 
    This is convenient if you intend to access the endpoint solely from your local machine.

## Run the configuration

When running a service, you can configure resources, and many [other options](../../docs/reference/api/python/index.md#dstack.api.RunCollection.submit).

```python
from dstack.api import Resources, GPU

run = client.runs.submit(
    run_name="codellama-34b-gptq", # (Optional) If unset, its chosen randomly
    configuration=configuration,
    resources=Resources(gpu=GPU(memory="24GB")),
)
```

## Access the endpoint

=== "Public endpoint"

    <div class="termy">
    
    ```shell
    $ curl https://&lt;run-name&gt;.&lt;domain-name&gt;/generate \
        -X POST \
        -d '{"inputs":"What is Deep Learning?","parameters":{"max_new_tokens": 20}}' \
        -H 'Content-Type: application/json'
    ```
    
    </div>

    > The OpenAPI documentation on the endpoint can be found at `https://<run-name>.<domain-name>/docs`.

=== "Private endpoint"

    <div class="termy">
    
    ```shell
    $ curl http://localhost:&lt;local-port&gt;/generate \
        -X POST \
        -d '{"inputs":"What is Deep Learning?","parameters":{"max_new_tokens": 20}}' \
        -H 'Content-Type: application/json'
    ```
    
    </div>

    > The OpenAPI documentation on the endpoint can be found at `http://localhost:<local-port>/docs`.

Both public and private endpoint support streaming, continuous batching, tensor parallelism, etc.

[//]: # (TODO: LangChain, own client)

## Manage runs

You can use the instance of [`dstack.api.Client`](../../docs/reference/api/python/index.md#dstack.api.Client) to manage your runs, 
including getting a list of runs, stopping a given run, etc.