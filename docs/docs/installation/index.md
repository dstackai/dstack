# Installation

[//]: # (??? info "dstack Sky")
[//]: # (    If you don't want to host the `dstack` server yourself or would like to access GPU from the `dstack` marketplace, you can use)
[//]: # (    `dstack`'s hosted version, proceed to [dstack Sky]&#40;#dstack-sky&#41;.)

To use the open-source version of `dstack` with your own cloud accounts or on-prem clusters, follow this guide.

> If you don't want to host the `dstack` server (or want to access GPU marketplace),
> skip installation and proceed to [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}.

### (Optional) Configure backends

To use `dstack` with your own cloud accounts, create the `~/.dstack/server/config.yml` file and 
[configure backends](../reference/server/config.yml.md). Alternatively, you can configure backends via the control plane UI after you start the server.

You can skip backends configuration if you intend to run containers  only on your on-prem servers. Use [SSH fleets](../concepts/fleets.md#ssh-fleets) for that.

## Start the server

Once backends are configured, proceed and start the server:

=== "pip"

    > The server can be set up via `pip` on Linux, macOS, and Windows (as long as you use WSL 2).
    > It requires Git and OpenSSH.

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

> For more details on server configuration options, see the
> [server deployment guide](../guides/server-deployment.md).

## Set up the CLI

Once it's up, you can use either the CLI or the API.

> The CLI can be set up on Linux, macOS, and Windows. It requires
> Git and OpenSSH.
    
??? info "Windows"
    To use the CLI on Windows, ensure you've installed Git and OpenSSH via 
    [Git for Windows:material-arrow-top-right-thin:{ .external }](https://git-scm.com/download/win){:target="_blank"}. 

    When installing it, ensure you've checked 
    `Git from the command line and also from 3-rd party software` 
    (or `Use Git and optional Unix tools from the Command Prompt`), and 
    `Use bundled OpenSSH`.

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

## What's next?

1. Check the [server/config.yml reference](../reference/server/config.yml.md) on how to configure backends
2. Check [SSH fleets](../concepts/fleets.md#ssh-fleets) to learn about running on your on-prem servers
3. Follow [quickstart](../quickstart.md)
4. Browse [examples](/examples)
5. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)