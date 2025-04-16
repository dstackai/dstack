# Quickstart

> Before using `dstack`, ensure you've [installed](installation/index.md) the server, or signed up for [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}.
    
## Initialize a repo

Before using `dstack`'s CLI in a directory, initialize the directory as a repo with [`dstack init`](reference/cli/dstack/init.md).

<div class="termy">

```shell
$ mkdir quickstart && cd quickstart
$ dstack init
```

</div>

## Apply a configuration

=== "Dev environment"

    A dev environment lets you provision an instance and access it with your desktop IDE.

    Create the following configuration file inside the repo:

    <div editor-title=".dstack.yml"> 

    ```yaml
    type: dev-environment
    name: vscode
    
    # If `image` is not specified, dstack uses its default image
    python: "3.11"
    #image: dstackai/base:py3.13-0.7-cuda-12.1
    
    ide: vscode
    
    # Uncomment to request resources
    #resources:
    #  gpu: 24GB
    ```

    </div>

    Apply the configuration via [`dstack apply`](reference/cli/dstack/apply.md):

    <div class="termy">

    ```shell
    $ dstack apply -f .dstack.yml
    
     #  BACKEND  REGION           RESOURCES                 SPOT  PRICE
     1  gcp      us-west4         2xCPU, 8GB, 100GB (disk)  yes   $0.010052
     2  azure    westeurope       2xCPU, 8GB, 100GB (disk)  yes   $0.0132
     3  gcp      europe-central2  2xCPU, 8GB, 100GB (disk)  yes   $0.013248
     
    Submit the run vscode? [y/n]: y
    
    Launching `vscode`...
    ---> 100%
    
    To open in VS Code Desktop, use this link:
      vscode://vscode-remote/ssh-remote+vscode/workflow
    ```
    
    </div>

    Open the link to access the dev environment using your desktop IDE.

    Alternatively, you can access it via `ssh <run name>`.

=== "Task"

    A task allows you to schedule a job or run a web app. Tasks can be distributed and can forward ports.

    Create the following configuration file inside the repo:

    <div editor-title="task.dstack.yml"> 

    ```yaml
    type: task
    name: streamlit
    
    # If `image` is not specified, dstack uses its default image
    python: "3.11"
    #image: dstackai/base:py3.13-0.7-cuda-12.1
    
    # Commands of the task
    commands:
      - pip install streamlit
      - streamlit hello
    # Ports to forward
    ports:
      - 8501

    # Uncomment to request resources
    #resources:
    #  gpu: 24GB
    ```

    </div>

    By default, tasks run on a single instance. To run a distributed task, specify 
    [`nodes`](concepts/tasks.md#distributed-tasks), and `dstack` will run it on a cluster.

    Run the configuration via [`dstack apply`](reference/cli/dstack/apply.md):

    <div class="termy">

    ```shell
    $ dstack apply -f task.dstack.yml
    
     #  BACKEND  REGION           RESOURCES                 SPOT  PRICE
     1  gcp      us-west4         2xCPU, 8GB, 100GB (disk)  yes   $0.010052
     2  azure    westeurope       2xCPU, 8GB, 100GB (disk)  yes   $0.0132
     3  gcp      europe-central2  2xCPU, 8GB, 100GB (disk)  yes   $0.013248
     
    Submit the run streamlit? [y/n]: y
    
    Provisioning `streamlit`...
    ---> 100%

      Welcome to Streamlit. Check out our demo in your browser.

      Local URL: http://localhost:8501
    ```
    
    </div>

    If you specified `ports`, they will be automatically forwarded to `localhost` for convenient access.

=== "Service"

    A service allows you to deploy a model or any web app as an endpoint.

    Create the following configuration file inside the repo:

    <div editor-title="service.dstack.yml"> 

    ```yaml
    type: service
    name: llama31-service
    
    # If `image` is not specified, dstack uses its default image
    python: "3.11"
    #image: dstackai/base:py3.13-0.7-cuda-12.1
    
    # Required environment variables
    env:
      - HF_TOKEN
    commands:
      - pip install vllm
      - vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct --max-model-len 4096
    # Expose the vllm server port
    port: 8000

    # Specify a name if it's an OpenAI-compatible model
    model: meta-llama/Meta-Llama-3.1-8B-Instruct
    
    # Required resources
    resources:
      gpu: 24GB
    ```

    </div>

    Run the configuration via [`dstack apply`](reference/cli/dstack/apply.md):

    <div class="termy">

    ```shell
    $ HF_TOKEN=...
    $ dstack apply -f service.dstack.yml
    
     #  BACKEND  REGION     INSTANCE       RESOURCES                    SPOT  PRICE
     1  aws      us-west-2  g5.4xlarge     16xCPU, 64GB, 1xA10G (24GB)  yes   $0.22
     2  aws      us-east-2  g6.xlarge      4xCPU, 16GB, 1xL4 (24GB)     yes   $0.27
     3  gcp      us-west1   g2-standard-4  4xCPU, 16GB, 1xL4 (24GB)     yes   $0.27
     
    Submit the run llama31-service? [y/n]: y
    
    Provisioning `llama31-service`...
    ---> 100%

    Service is published at: 
      http://localhost:3000/proxy/services/main/llama31-service/
    Model meta-llama/Meta-Llama-3.1-8B-Instruct is published at:
      http://localhost:3000/proxy/models/main/
    ```
    
    </div>

    !!! info "Gateway"
        To enable [auto-scaling](concepts/services.md#replicas-and-scaling),
        [rate limits](concepts/services.md#rate-limits),
        or use a custom domain with HTTPS, 
        set up a [gateway](concepts/gateways.md) before running the service.
        If you're using [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
        a gateway is pre-configured for you.

> `dstack apply` automatically provisions instances, uploads the contents of the repo (incl. your local uncommitted changes),
and runs the configuration.

## Troubleshooting

Something not working? See the [troubleshooting](guides/troubleshooting.md) guide.

!!! info "What's next?"
    1. Read about [backends](concepts/backends.md),  [dev environments](concepts/dev-environments.md), [tasks](concepts/tasks.md), and [services](concepts/services.md)
    2. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)
    3. Browse [examples](https://dstack.ai/examples)
