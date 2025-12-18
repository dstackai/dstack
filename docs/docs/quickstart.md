# Quickstart

??? info "Prerequsites"
    Before using `dstack`, ensure you've [installed](installation/index.md) the server and the CLI.

## Create a fleet

Before you can submit your first run, you have to create a [fleet](concepts/fleets.md). 

=== "Backend fleet"
    If you're using cloud providers or Kubernetes clusters and have configured the corresponding [backends](concepts/backends.md), create a fleet as follows:

    <div editor-title="fleet.dstack.yml"> 

    ```yaml
    type: fleet
    name: default

    # Allow to provision of up to 2 instances
    nodes: 0..2

    # Deprovision instances above the minimum if they remain idle
    idle_duration: 1h

    resources:
      # Allow to provision up to 8 GPUs
      gpu: 0..8
    ```

    </div>

    Pass the fleet configuration to `dstack apply`:

    <div class="termy">

    ```shell
    $ dstack apply -f fleet.dstack.yml
        
      #  BACKEND  REGION           RESOURCES                 SPOT  PRICE
      1  gcp      us-west4         2xCPU, 8GB, 100GB (disk)  yes   $0.010052
      2  azure    westeurope       2xCPU, 8GB, 100GB (disk)  yes   $0.0132
      3  gcp      europe-central2  2xCPU, 8GB, 100GB (disk)  yes   $0.013248

    Create the fleet? [y/n]: y

      FLEET    INSTANCE  BACKEND  RESOURCES  PRICE  STATUS  CREATED 
      defalut  -         -        -          -      -       10:36
    ```

    </div>

    If `nodes` is a range that starts above `0`, `dstack` pre-creates the initial number of instances up front, while any additional ones are created on demand. 
    
    > Setting the `nodes` range to start above `0` is supported only for [VM-based backends](concepts/backends.md#vm-based).

    If the fleet needs to be a cluster, the [placement](concepts/fleets.md#backend-placement) property must be set to `cluster`. 
    
=== "SSH fleet"
    If you have a group of on-prem servers accessible via SSH, you can create an SSH fleet as follows:

    <div editor-title="fleets.dstack.yml"> 
    
    ```yaml
    type: fleet
    name: my-fleet

    ssh_config:
      user: ubuntu
      identity_file: ~/.ssh/id_rsa
      hosts:
        - 3.255.177.51
        - 3.255.177.52
    ```
      
    </div>

    Pass the fleet configuration to `dstack apply`:

    <div class="termy">

    ```shell
    $ dstack apply -f fleet.dstack.yml
        
    Provisioning...
    ---> 100%

      FLEET     INSTANCE  GPU             PRICE  STATUS  CREATED 
      my-fleet  0         L4:24GB (spot)  $0     idle    3 mins ago      
                1         L4:24GB (spot)  $0     idle    3 mins ago    
    ```

    </div>

    > Hosts must have Docker and GPU drivers installed and meet the other [requirements](concepts/fleets.md#ssh-fleets).

    If the fleet needs to be a cluster, the [placement](concepts/fleets.md#ssh-placement) property must be set to `cluster`.

## Submit your first run

`dstack` supports three types of run configurations.

=== "Dev environment"
    A [dev environment](concepts/dev-environments.md) lets you provision an instance and access it with your desktop IDE.

    Create the following run configuration:

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

    Apply the configuration via `dstack apply`:

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

    Open the link to access the dev environment using your desktop IDE. Alternatively, you can access it via `ssh <run name>`.

=== "Task"
    A [task](concepts/tasks.md) allows you to schedule a job or run a web app. Tasks can be distributed and can forward ports.

    Create the following run configuration:

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

    Run the configuration via `dstack apply`:

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
    A [service](concepts/services.md) allows you to deploy a model or any web app as an endpoint.

    Create the following run configuration:

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

    Run the configuration via `dstack apply`:

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

    > To enable auto-scaling rate limits, or use a custom domain with HTTPS, set up a [gateway](concepts/gateways.md) before running the service.

`dstack apply` automatically provisions instances with created fleets and runs the workload according to the configuration.

## Troubleshooting

Something not working? See the [troubleshooting](guides/troubleshooting.md) guide.

!!! info "What's next?"
    1. Read about [backends](concepts/backends.md),  [dev environments](concepts/dev-environments.md), [tasks](concepts/tasks.md), [services](concepts/services.md), and [fleets](concepts/services.md)
    2. Browse [examples](../examples.md)
    3. Join [Discord](https://discord.gg/u8SmfwPpMd)
