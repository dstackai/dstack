# Quickstart

`dstack` is an open-source platform that simplifies 
training, fine-tuning, and deploying generative AI models, leveraging the open-source 
ecosystem.

## Installation

To use `dstack`, either set up the open-source server (and configure your own cloud accounts)
or use the cloud version (which provides GPU out of the box).

??? info "Install open-source"

    If you wish to use `dstack` with your own cloud accounts, you can set up the open-source server.

    ### Install the server
    
    The easiest way to install the server, is via `pip`:
    
    <div class="termy">
    
    ```shell
    $ pip install "dstack[all]" -U
    ```
    
    </div>
    
    > Another way to install the server is through [Docker](https://hub.docker.com/r/dstackai/dstack).
    
    ### Configure the server
    
    If you have default AWS, GCP, or Azure credentials on your machine, the `dstack` server will pick them up automatically.
    
    Otherwise, you need to manually specify the cloud credentials in `~/.dstack/server/config.yml`.
    For further details, refer to [server configuration](configuration/server.md).
    
    ### Start the server
    
    To start the server, use the `dstack server` command:
    
    <div class="termy">
    
    ```shell
    $ dstack server
    
    Applying configuration...
    ---> 100%
    
    The server is running at http://127.0.0.1:3000/.
    The admin token is bbae0f28-d3dd-4820-bf61-8f4bb40815da
    ```
    
    </div>

    #### Client configuration

    At startup, the server automatically configures CLI and API with the server address, user token, and 
    the default project name (`main`). 

    To use CLI and API on different machines or projects,
    use [`dstack config`](reference/cli/index.md#dstack-config).

    <div class="termy">
    
    ```shell
    $ dstack config --server &lt;your server adddress&gt; \
        --project &lt;your project name&gt; \
        --token &lt;your user token&gt;
    ```
    
    </div>

    The client configuration is stored via `~/.dstack/config.yml`.

??? info "Use the cloud GPU"
    
    If you want `dstack` to provide cloud GPU, 
    <a href="#" data-tally-open="w7K17R">sign up</a> for the cloud version of `dstack`, and configure the client 
    with server address, user token, and project name using `dstack config`.

    <div class="termy">
    
    ```shell
    $ dstack config --server https://cloud.dstack.ai \
        --project &lt;your project name&gt; \
        --token &lt;your user token&gt;
    ```
    
    </div>

    The client configuration is stored via `~/.dstack/config.yml`.
    
Once `dstack` is set up, you can use CLI or API.

## Using the API

### Create a client

<div editor-title="">

```python
from dstack.api import Client

client = Client.from_config()
```

</div>

### Submit a run

=== "Fine-tuning"

    ```python
    from dstack.api import Resources, GPU
    from dstack.api.finetuning import SFTFineTuningTask

    # Specify a HuggingFace model and dataset and training params

    task = SFTFineTuningTask(
        hf_model_name="NousResearch/Llama-2-13b-hf",
        hf_dataset_name="peterschmidt85/samsum",
        hf_token="...",
        num_train_epochs=2
    )

    run = client.runs.submit(
        configuration=task,
        resources=Resources(gpu=GPU(memory="24GB"))
    )
    ```

    > Go to [Fine-tuning](guides/fine-tuning.md) to learn more.

## Using the CLI

The CLI allows you to define configurations (what you want to run) as YAML files and run them using the `dstack run`
command.

### Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `train.dstack.yml`
are both acceptable).

=== "Dev environment"

    ```yaml
    type: dev-environment

    python: "3.11" # (Optional) If not specified, your local version is used
    
    ide: vscode
    ```

    > Go to [Dev environments](guides/dev-environments.md) to learn more.

=== "Task"

    ```yaml
    type: task

    ports:
      - 7860
    
    python: "3.11" # (Optional) If not specified, your local version is used.
    
    commands:
      - pip install -r requirements.txt
      - gradio app.py
    ```

    > Go to [Tasks](guides/tasks.md) to learn more.

=== "Service"

    ```yaml
    type: service

    image: ghcr.io/huggingface/text-generation-inference:latest
    
    env: 
      - MODEL_ID=TheBloke/Llama-2-13B-chat-GPTQ 
    
    port: 80
    
    commands:
      - text-generation-launcher --hostname 0.0.0.0 --port 80 --trust-remote-code
    ```

    > Go to [Services](guides/services.md) to learn more.

### Run the configuration

To run a configuration, use the `dstack run` command followed by the working directory path, 
configuration file path, and any other options (e.g., for requesting hardware resources).

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml --gpu A100

 BACKEND     REGION         RESOURCES                     SPOT  PRICE
 tensordock  unitedkingdom  10xCPU, 80GB, 1xA100 (80GB)   no    $1.595
 azure       westus3        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 azure       westus2        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 
Continue? [y/n]: y

Provisioning...
---> 100%

Epoch 0:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 1:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 2:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
```

</div>

No need to worry about copying code, setting up environment, IDE, etc. `dstack` handles it all 
automatically.