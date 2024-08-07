# Quickstart

> Before using `dstack`, [install](installation/index.md) the server.
    
## Initialize a repo

To use `dstack`'s CLI in a folder, first run [`dstack init`](reference/cli/index.md#dstack-init) within that folder.

<div class="termy">

```shell
$ mkdir quickstart && cd quickstart
$ dstack init
```

</div>

Your folder can be a regular local folder or a Git repo.

## Run a configuration

=== "Dev environment"

    A dev environment lets you provision a remote machine with your code, dependencies, and resources, and access it 
    with your desktop IDE.

    ##### Define a configuration

    Create the following configuration file inside the repo:

    <div editor-title=".dstack.yml"> 

    ```yaml
    type: dev-environment
    # The name is optional, if not specified, generated randomly
    name: vscode
    
    python: "3.11"
    # Uncomment to use a custom Docker image
    #image: dstackai/base:py3.10-0.4-cuda-12.1
    
    ide: vscode
    
    # Use either spot or on-demand instances
    spot_policy: auto
    
    # Uncomment to request resources
    #resources:
    #  gpu: 24GB
    ```

    </div>

    ##### Run the configuration

    Run the configuration via [`dstack apply`](reference/cli/index.md#dstack-apply):

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

=== "Task"

    A task allows you to schedule a job or run a web app. It lets you configure 
    dependencies, resources, ports, the number of nodes (if you want to run the task on a cluster), etc.

    ##### Define a configuration

    Create the following configuration file inside the repo:

    <div editor-title="streamlit.dstack.yml"> 

    ```yaml
    type: task
    # The name is optional, if not specified, generated randomly
    name: streamlit
    
    python: "3.11"
    # Uncomment to use a custom Docker image
    #image: dstackai/base:py3.10-0.4-cuda-12.1
    
    # Commands of the task
    commands:
      - pip install streamlit
      - streamlit hello
    # Ports to forward
    ports:
      - 8501

    # Use either spot or on-demand instances
    spot_policy: auto
    
    # Uncomment to request resources
    #resources:
    #  gpu: 24GB
    ```

    </div>

    ##### Run the configuration

    Run the configuration via [`dstack apply`](reference/cli/index.md#dstack-apply):

    <div class="termy">

    ```shell
    $ dstack apply -f streamlit.dstack.yml
    
     #  BACKEND  REGION           RESOURCES                 SPOT  PRICE
     1  gcp      us-west4         2xCPU, 8GB, 100GB (disk)  yes   $0.010052
     2  azure    westeurope       2xCPU, 8GB, 100GB (disk)  yes   $0.0132
     3  gcp      europe-central2  2xCPU, 8GB, 100GB (disk)  yes   $0.013248
     
    Submit the run streamlit? [y/n]: y
     
    Continue? [y/n]: y
    
    Provisioning `streamlit`...
    ---> 100%

      Welcome to Streamlit. Check out our demo in your browser.

      Local URL: http://localhost:8501
    ```
    
    </div>

    `dstack apply` automatically forwards the remote ports to `localhost` for convenient access.

=== "Service"

    A service allows you to deploy a web app or a model as a scalable endpoint. It lets you configure
    dependencies, resources, authorizarion, auto-scaling rules, etc. 

    ??? info "Prerequisites"
        If you're using the open-source server, you must set up a [gateway](concepts/gateways.md) before you can run a service.

        If you're using [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
        the gateway is already set up for you.

    ##### Define a configuration

    Create the following configuration file inside the repo:

    <div editor-title="streamlit-service.dstack.yml"> 

    ```yaml
    type: service
    # The name is optional, if not specified, generated randomly
    name: streamlit-service
    
    python: "3.11"
    # Uncomment to use a custom Docker image
    #image: dstackai/base:py3.10-0.4-cuda-12.1
    
    # Commands of the service
    commands:
      - pip install streamlit
      - streamlit hello
    # Port of the service
    port: 8501

    # Comment to enable authorizartion
    auth: False

    # Use either spot or on-demand instances
    spot_policy: auto
    
    # Uncomment to request resources
    #resources:
    #  gpu: 24GB
    ```

    </div>

    ##### Run the configuration

    Run the configuration via [`dstack apply`](reference/cli/index.md#dstack-apply):

    <div class="termy">

    ```shell
    $ dstack apply -f streamlit.dstack.yml
    
     #  BACKEND  REGION           RESOURCES                 SPOT  PRICE
     1  gcp      us-west4         2xCPU, 8GB, 100GB (disk)  yes   $0.010052
     2  azure    westeurope       2xCPU, 8GB, 100GB (disk)  yes   $0.0132
     3  gcp      europe-central2  2xCPU, 8GB, 100GB (disk)  yes   $0.013248
     
    Submit the run streamlit? [y/n]: y
     
    Continue? [y/n]: y
    
    Provisioning `streamlit`...
    ---> 100%

      Welcome to Streamlit. Check out our demo in your browser.

      Local URL: https://streamlit-service.example.com
    ```
    
    </div>

    One the service is up, its endpoint is accessible at `https://<run name>.<gateway domain>`.

> `dstack apply` automatically uploads the code from the current repo, including your local uncommitted changes.

## What's next?

1. Read about [dev environments](dev-environments.md), [tasks](tasks.md), 
    [services](services.md), and [fleets](fleets.md) 
2. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}
3. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)

!!! info "Examples"
    To see how dev environments, tasks, services, and fleets can be used for 
    training and deploying AI models, check out the [examples](examples/index.md).