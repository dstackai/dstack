# Installation

[//]: # (??? info "dstack Sky")
[//]: # (    If you don't want to host the `dstack` server yourself or would like to access GPU from the `dstack` marketplace, you can use)
[//]: # (    `dstack`'s hosted version, proceed to [dstack Sky]&#40;#dstack-sky&#41;.)

To use the open-source version of `dstack` with your own cloud accounts or on-prem servers, 
you have to set up the server. 

## Set up the server

Follow the steps below to set up the server.

### 1. Configure backends

> If you want the `dstack` server to run containers or manage clusters in your cloud accounts (or use Kubernetes),
create the [~/.dstack/server/config.yml](../reference/server/config.yml.md) file and configure backends.

### 2. Start the server

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

> By default, the `dstack` server stores its state in `~/.dstack/server/data` using SQLite.
> To use a database, set the [`DSTACK_DATABASE_URL`](../reference/cli/index.md#environment-variables) environment variable.

The server can be set up anywhere: on your laptop, a dedicated server, or in the cloud.
Once the `dstack` server is up, you can use the CLI or API.

### 3. Set up the CLI

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

### 4. Add on-prem servers
    
!!! info "Fleets"
    If you want the `dstack` server to run containers on your on-prem servers,
    use [fleets](../fleets.md#__tabbed_1_2).

## dstack Sky

If you don't want to host the `dstack` server yourself or would like to access GPU from the `dstack` marketplace, sign up with
[dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}.

### Set up the CLI

If you've signed up,
open your project settings, and copy the `dstack config` command to point the CLI to the project.

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

### Configure clouds

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