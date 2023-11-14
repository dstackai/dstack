# Text generation

For deploying an LLM with `dstack`'s API, specify a model, quantization parameters, 
and required compute resources. `dstack` takes care of everything else.

??? info "Prerequisites"
    If you're using the open-source server, before using the model serving API, make sure to
    [set up a gateway](services.md#set-up-a-gateway).

    If you're using the cloud version of `dstack`, it's set up automatically for you.

    Also, to use the model serving API, ensure you have the latest version:

    <div class="termy">

    ```shell
    $ pip install "dstack[all]==0.12.3rc1"
    ```

    </div>

## Create a client

First, you connect to `dstack`:

```python
from dstack.api import Client, ClientError

try:
    client = Client.from_config()
except ClientError:
    print("Can't connect to the server")
```

## Create a service

Then, you create a completion service, specifying the model, and quantization parameters.

```python
from dstack.api import CompletionService

service = CompletionService(
    model_name="TheBloke/CodeLlama-34B-GPTQ",
    quantize="gptq"
)
```

## Run the service

When running a service, you can configure resources, and many [other options](../../docs/reference/api/python/index.md#dstack.api.RunCollection.submit).

```python
from dstack.api import Resources, GPU

run = client.runs.submit(
    run_name="codellama-34b-gptq", # (Optional) If unset, its chosen randomly
    configuration=service,
    resources=Resources(gpu=GPU(memory="24GB")),
)
```

## Access the endpoint

Once the model is deployed, its endpoint will be available at
`https://<run-name>.<domain-name>` (using the domain set up for the gateway).

<div class="termy">

```shell
$ curl https://&lt;run-name&gt;.&lt;domain-name&gt;/generate \
    -X POST \
    -d '{"inputs":"What is Deep Learning?","parameters":{"max_new_tokens": 20}}' \
    -H 'Content-Type: application/json'
```

</div>

> The endpoint supports streaming, continuous batching, tensor parallelism, etc.

The OpenAI documentation on the endpoint can be found at `https://<run-name>.<domain-name>/docs`.

[//]: # (TODO: LangChain, own client)

## Manage runs

You can use the instance of [`dstack.api.Client`](../../docs/reference/api/python/index.md#dstack.api.Client) to manage your runs, 
including getting a list of runs, stopping a given run, etc.