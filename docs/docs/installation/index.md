# Installation

To use the open-source version of `dstack` (which is self-hosted to use your own cloud accounts or data centers), 
go ahead and [set up the server](#set-up-the-server). 

To use [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}
(a managed service that allows you to use either GPUs via marketplace, or connect to your own cloud accounts or data centers), 
proceed to [dstack Sky](#dstack-sky).

## Set up the server

### Configure backends

Before starting the `dstack` server, create `~/.dstack/server/config.yml` and
configure a backend for each cloud account that you'd like to use.

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
  - name: main
    backends:
      - type: aws
        creds:
          type: access_key
          access_key: AIZKISCVKUKO5AAKLAEH
          secret_key: QSbmpqJIUBn1V5U3pyM9S6lwwiu8/fOJ2dgfwFdW
```

</div>

> Go to the [server/config.yml reference](../reference/server/config.yml.md#examples)
> for details on how to configure backends for AWS, GCP, Azure, OCI, Lambda, 
> TensorDock, Vast.ai, RunPod, CUDO, Kubernetes, etc.

### Start the server

Once the `~/.dstack/server/config.yml` file is configured, proceed to start the server:

=== "pip"

    <div class="termy">
    
    ```shell
    $ pip install "dstack[all]" -U
    $ dstack server

    Applying ~/.dstack/server/config.yml...

    The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
    The server is running at http://127.0.0.1:3000/
    ```
    
    </div>

=== "Docker"

    <div class="termy">
    
    ```shell
    $ docker run -p 3000:3000 \
        -v $HOME/.dstack/server/:/root/.dstack/server \
        dstackai/dstack

    Applying ~/.dstack/server/config.yml...

    The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
    The server is running at http://127.0.0.1:3000/
    ```
        
    </div>

    > For more details on how to deploy `dstack` using Docker, check its [Docker repo](https://hub.docker.com/r/dstackai/dstack).

> By default, `dstack` stores its state in `~/.dstack/server/data` using SQLite.
> To use a database, set the [`DSTACK_DATABASE_URL`](../reference/cli/index.md#environment-variables) environment variable.

Once the `dstack` server is up, feel free to use the CLI or API to work with it.

### Set up the CLI

To point the CLI to the `dstack` server, configure it
with the server address, user token and project name:

<div class="termy">

```shell
$ pip install dstack
$ dstack config --url http://127.0.0.1:3000 \
    --project main \
    --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
    
Configuration is updated at ~/.dstack/config.yml
```

</div>

This configuration is stored in `~/.dstack/config.yml`.

### Add on-prem clusters
    
If you'd like to use `dstack` to run workloads on your on-prem clusters,
check out the [dstack pool add-ssh](../concepts/pools.md#adding-on-prem-clusters) command.

## dstack Sky

### Set up the CLI

If you've signed up with [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
open the project settings, and copy the `dstack config` command to point the CLI to the project.

![](https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-sky-project-config.png){ width=800 }

Then, install the CLI on your machine and use the copied command.

<div class="termy">

```shell
$ pip install dstack
$ dstack config --url https://sky.dstack.ai \
    --project peterschmidt85 \
    --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
    
Configuration is updated at ~/.dstack/config.yml
```

</div>

### Configure backends

By default, [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"} 
uses the GPU from its marketplace, which requires a credit card to be attached in your account
settings.

To use your own cloud accounts, click the settings icon of the corresponding backend and specify credentials:

![](https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-sky-edit-backend-config.png){ width=800 }

[//]: # (The `dstack server` command automatically updates `~/.dstack/config.yml`)
[//]: # (with the `main` project.)

## What's next?

1. Check the [server/config.yml reference](../reference/server/config.yml.md) on how to configure backends
2. Follow [quickstart](../quickstart.md)
3. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples)
4. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)