# Installation

> If you don't want to host the `dstack` server (or want to access GPU marketplace),
> skip installation and proceed to [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}.

## Set up the server

### (Optional) Configure backends

Backends allow `dstack` to manage compute across various providers.
They can be configured via `~/.dstack/server/config.yml` (or through the [project settings page](../concepts/projects.md#backends) in the UI).

For more details on how to configure backends, check [Backends](../concepts/backends.md).

??? info "SSH fleets"
    For using `dstack` with on-prem servers, create [SSH fleets](../concepts/fleets.md#ssh) 
    once the server is up.

### Start the server

The server can run on your laptop or any environment with access to the cloud and on-prem clusters you plan to use.

=== "uv"

    > The server can be set up via `uv` on Linux, macOS, and Windows (via WSL 2).
    > It requires Git and OpenSSH.

    <div class="termy">
    
    ```shell
    $ uv tool install "dstack[all]" -U
    $ dstack server

    Applying ~/.dstack/server/config.yml...

    The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
    The server is running at http://127.0.0.1:3000/
    ```
    
    </div>

=== "pip"

    > The server can be set up via `pip` on Linux, macOS, and Windows (via WSL 2).
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

To verify that backends are properly configured, use the [`dstack offer`](../reference/cli/dstack/offer.md#list-gpu-offers) command to list available GPU offers.

!!! info "Server deployment"
    For more details on server deployment options, see the
    [Server deployment](../guides/server-deployment.md) guide.

## Set up the CLI

Once the server is up, you can access it via the `dstack` CLI. 

> The CLI can be set up via `pip` or `uv` on Linux, macOS, and Windows. It requires Git and OpenSSH.

=== "uv"

    <div class="termy">
    
    ```shell
    $ uv tool install dstack -U
    ```

    </div>

=== "pip"

    <div class="termy">
    
    ```shell
    $ pip install dstack -U
    ```

    </div>

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
$ dstack project add \
    --name main \
    --url http://127.0.0.1:3000 \
    --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
    
Configuration is updated at ~/.dstack/config.yml
```

</div>

This configuration is stored in `~/.dstack/config.yml`.

??? info "Shell autocompletion"

    `dstack` supports shell autocompletion for `bash` and `zsh`.

    === "bash"

        First, validate if completion scripts load correctly in your current shell session:
        
        <div class="termy">
        
        ```shell
        $ eval "$(dstack completion bash)"
        ```

        </div>
        
        If completions work as expected and you would like them to persist across shell sessions, add the completion script to your shell profile using these commands:
        
        <div class="termy">
        
        ```shell
        $ mkdir -p ~/.dstack
        $ dstack completion bash > ~/.dstack/completion.sh
        $ echo 'source ~/.dstack/completion.sh' >> ~/.bashrc
        ```
        
        </div>

    === "zsh"
        
        First, validate if completion scripts load correctly in your current shell session:
        
        <div class="termy">
        
        ```shell
        $ eval "$(dstack completion zsh)"
        ```

        </div>
        
        If completions work as expected and you would like them to persist across shell sessions, you can install them via Oh My Zsh using these commands:
        
        <div class="termy">
        
        ```shell
        $ mkdir -p ~/.oh-my-zsh/completions
        $ dstack completion zsh > ~/.oh-my-zsh/completions/_dstack
        ```
            
        </div>

        And if you don't use Oh My Zsh:

        <div class="termy">
        
        ```shell
        $ mkdir -p ~/.dstack
        $ dstack completion zsh > ~/.dstack/completion.sh
        $ echo 'source ~/.dstack/completion.sh' >> ~/.zshrc
        ```
        
        </div>

        > If you get an error similar to `2: command not found: compdef`, then add the following line to the beginning of your `~/.zshrc` file:
        > `autoload -Uz compinit && compinit`.
    

!!! info "What's next?"
    1. Follow [Quickstart](../quickstart.md)
    2. See [Backends](../concepts/backends.md)
    3. Check the [server deployment](../guides/server-deployment.md) guide
    4. Browse [examples](/examples)
    5. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)
