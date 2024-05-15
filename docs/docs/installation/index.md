# Installation

To install `dstack`, use `pip`:

<div class="termy">
    
    ```shell
    $ pip install "dstack[all]" -U
    ```

</div>

## Configure backends

Before you can start the `dstack` server and let it provision instances in your cloud accounts, you have to
create the `~/.dstack/server/config.yml` file and configure a backend for each cloud account.

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

> See the [server/config.yml reference](../reference/server/config.yml.md#examples)
> for more details on how to configure backends for all supported cloud providers.

## Start the server

Once the `~/.dstack/server/config.yml` file is configured, proceed to start the server:

=== "pip"

    <div class="termy">
    
    ```shell
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

Once the `dstack` server is up, feel free to use the CLI or API to work with it.

## Configure the CLI

To point the CLI to the `dstack` server, configure `~/.dstack/config.yml`
with the server address, user token and project name:

<div class="termy">

```shell
$ dstack config --url http://127.0.0.1:3000 \
    --project main \
    --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
    
Configuration is updated at ~/.dstack/config.yml
```

</div>

[//]: # (The `dstack server` command automatically updates `~/.dstack/config.yml`)
[//]: # (with the `main` project.)

## What's next?

1. Check the [`server/config.yml` reference](../reference/server/config.yml.md) on how to configure backends
2. Follow [quickstart](../quickstart.md)
3. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples)
4. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)