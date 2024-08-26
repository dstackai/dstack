# Installation

[//]: # (??? info "dstack Sky")
[//]: # (    If you don't want to host the `dstack` server yourself or would like to access GPU from the `dstack` marketplace, you can use)
[//]: # (    `dstack`'s hosted version, proceed to [dstack Sky]&#40;#dstack-sky&#41;.)

To use the open-source version of `dstack` with your own cloud accounts or on-prem clusters, follow this guide.

> If you don't want to host the `dstack` server or want to access affordable GPU from the marketplace,
> skip installation and proceed to [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}.

## Configure backends

To use `dstack` with your own cloud accounts, or Kubernetes,
create the [`~/.dstack/server/config.yml`](../reference/server/config.yml.md) file and configure backends.

## Start the server

Once the `~/.dstack/server/config.yml` file is configured, proceed and start the server:

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

The `dstack` server can run anywhere: on your laptop, a dedicated server, or in the cloud. Once it's up, you
can use either the CLI or the API.

??? info "State"
    By default, the `dstack` server stores its state locally in `~/.dstack/server`.
    To store it externally, use the `DSTACK_DATABASE_URL` and 
    `DSTACK_SERVER_CLOUDWATCH_LOG_GROUP` [environment variables](../reference/cli/index.md#environment-variables).

    If you want backend credentials and user tokens to be encrypted, you can set up encryption keys via
    [`~/.dstack/server/config.yml`](../reference/server/config.yml.md#encryption_1).

## Set up the CLI

To point the CLI to the `dstack` server, configure it
with the server address, user token, and project name:

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

## Create on-prem fleets

If you want the `dstack` server to run containers on your on-prem clusters,
use [on-fleets](../fleets.md#__tabbed_1_2).

## What's next?

1. Check the [server/config.yml reference](../reference/server/config.yml.md) on how to configure backends
2. Follow [quickstart](../quickstart.md)
3. Browse [examples](/examples)
4. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)