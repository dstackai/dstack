# Dev environments

A dev environment is a cloud instance pre-configured with an IDE.
It is ideal when you want to interactively work with code using your favorite IDE.

## Using the CLI

### Define a configuration

To run a dev environment via the CLI, first create its configuration file. 
The configuration file name must end with `.dstack.yml` (e.g., `.dstack.yml` or `dev.dstack.yml` are both acceptable).

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

python: "3.11" # (Optional) If not specified, your local version is used

ide: vscode
```

</div>

By default, `dstack` uses its own Docker images to run dev environments, 
which are pre-configured with Python, Conda, and essential CUDA drivers.

!!! info "Configuration options"
    Configuration file allows you to specify a custom Docker image, ports, environment variables, and many other 
    options.
    For more details, refer to the [Reference](../reference/dstack.yml/dev-environment.md).

### Run the configuration

The `dstack run` command requires the working directory path, and optionally, the `-f`
argument pointing to the configuration file.

If the `-f` argument is not specified, `dstack` looks for the default configuration (`.dstack.yml`) in the working directory.

<div class="termy">

```shell
$ dstack run . --gpu A100

 RUN          CONFIGURATION  BACKEND  RESOURCES        SPOT  PRICE
 fast-moth-1  .dstack.yml    aws      5xCPUs, 15987MB  yes   $0.0547 
 
Provisioning and starting SSH tunnel...
---> 100%

To open in VS Code Desktop, use this link:
  vscode://vscode-remote/ssh-remote+fast-moth-1/workflow
```

</div>

After you run it, `dstack` provides a URL to open the dev environment in your desktop VS Code.

![](../../assets/images/dstack-vscode-jupyter.png){ width=800 }

By default, the dev environment comes with pre-installed Python and Jupyter extensions.

#### Request resources

The `dstack run` command allows you to use `--gpu` to request GPUs (e.g. `--gpu A100` or `--gpu 80GB` or `--gpu A100:4`, etc.),
`--memory` to request memory (e.g. `--memory 128GB`),
and many other options (incl. spot instances, max price, max duration, retry policy, etc.).

For more details on the `dstack run` command, refer to the [Reference](../reference/cli/run.md).