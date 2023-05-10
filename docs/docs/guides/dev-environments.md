# Dev environments

A dev environment is a virtual machine that can be launched based on a pre-defined configuration. Depending on the
configured project, you can launch dev environments either locally or in a cloud account of your choice. If launched in
the cloud, `dstack` takes care of creating cloud resources, saving data, and cleaning up when the dev environment is
stopped.

[//]: # (TODO [TASK]: Add a link to the Playground)

## Creating a configuration file

A configuration can be defined as a YAML file (under the `.dstack/workflows` directory).

<div editor-title=".dstack/workflows/hello-env.yaml"> 

```yaml
workflows:
  - name: hello-env
    provider: code
    python: 3.11
    setup:
      - pip install transformers accelerate gradio
    resources:
      gpu:
        name: V100
        count: 1
```

</div>

[//]: # (TODO [MAJOR]: It doesn't allow to conveniently load and save artifacts)

## Running and stopping a dev environment

Once a configuration is defined, you can launch it using the `dstack run` command:

<div class="termy">

```shell
$ dstack run hello-env

RUN      WORKFLOW   SUBMITTED  STATUS     TAG
shady-1  hello-env  now        Submitted  
 
Starting SSH tunnel...

To exit, press Ctrl+C.

Web UI available at http://127.0.0.1:51845/?tkn=4d9cc05958094ed2996b6832f899fda1
```

</div>

For convenience, `dstack` uses an exact copy of the source code that is locally present in the folder where you use the `dstack` command.

[//]: # (TODO [TASK]: A screenshot)

??? info "Configuring projects"
    The default project is configured to run dev environments locally. However, you can
    log into Hub and configure additional projects to run dev environments in a cloud account of your choice. 

    You can configure multiple projects and pass the project name to the CLI by using the `--project` argument.

[//]: # (TODO [TASK]: Add a link to the Projects guide for more details)

[//]: # (TODO [TASK]: Add links to the CLI reference for the commands and their options)

#### Stopping a dev environment 

To stop a dev environment, click `Ctrl`+`C` while the `dstack run` command is running,
or use the `dstack stop` command.

## Supported IDEs

Out of the box, `dstack` allows you to launch VS Code, JupyterLab, and Jupyter notebooks.
All you have to do is to set the `provider` property in the YAML configuration accordingly:

- `code` – VS Code
- `lab` - JupyterLab
- `notebook` – Jupyter notebook

[//]: # (TODO [TASK]: Use content tabs to show multiple examples - requires fixing CSS styles)

If you use this configuration, `dstack` sets up the IDE automatically, forwards
its port to your local machine and prints the URL to access it in the output.

#### Connecting via SSH

Alternatively, you can use the `bash` provider with SSH enabled to attach any desktop IDE to the dev
environment.

<div editor-title=".dstack/workflows/hello-ssh.yaml"> 

```yaml
  workflows:
  - name: hello-ssh
    provider: bash
    commands:
      - tail -f /dev/null
    ssh: true 
```

</div>

[//]: # (TODO [MEDIUM]: Currently, you have to use bash and tail)

[//]: # (TODO [TASK]: Show the output)

When you run it, `dstack` forwards the SSH port to your local machine and prints the SSH command for connecting. 
Then, you can either attach your desktop VS Code or PyCharm, or connect from a terminal.

[//]: # (TODO [MAJOR]: Currently, it doesn't support PyCharm)

## Configuring hardware resources

If your project is configured to run dev environments in the cloud, you can use the `resources` property in the YAML 
file to request hardware resources like memory, GPUs, and shared memory size. 

Additionally, you can choose whether `dstack` should use interruptible instances (also known as spot instances).

<div editor-title=".dstack/workflows/hello-resources.yaml"> 

```yaml
workflows:
  - name: hello-resources
    provider: code
    resources:
      gpu:
        name: V100
        count: 8
      interruptible: true
```

</div>

[//]: # (TODO [MAJOR]: Currently, it doesn't allow you to specify interruptible behaviour, e.g. "spot or fail" or "spot or on-demand")

See the [reference page](../reference/providers/code.md#resources) for details.

## Setting up the environment

You can use the `setup` property in the YAML file to pre-install packages or run other bash commands during environment
startup.

Use `python` property to specify a version of Python for pre-installation. Otherwise, `dstack` uses the local version.

<div editor-title=".dstack/workflows/hello-setup.yaml"> 

```yaml
workflows:
  - name: hello-setup
    provider: code
    python: "3.11"
    setup:
      - conda install pandas
```

</div>

!!! info "NOTE:"
    You can use `pip` and `conda` executables to install packages and set up the environment.

[//]: # (TODO [MAJOR]: Currently, packages has to be installed on every run)

[//]: # (TODO [MAJOR]: Currently, there is no way to use your own Docker image)

## Exposing ports

To run web apps in the dev environment and access them locally, specify port numbers with the `ports` property. They'll be
passed to the dev environment as environment variables like `PORT_0`, `PORT_1`, etc.

[//]: # (TODO [TASK]: Requires an example, including the YAML and the output)

`dstack` will automatically forward ports to your local machine. You'll see the URLs to access each port in the
output.

[//]: # (TODO [MEDIUM]: It's not convenient to use dstack environment variables for ports)
[//]: # (TODO [MEDIUM]: It would be easier if dstack forwarded ports automatically)

## Configuring cache

When working in a dev environment, you may need to download files like pre-trained models, external data, or Python
packages. If you restart the environment, you may have to download them again. To avoid this, `dstack` lets you choose
which paths to cache between runs. 

<div editor-title=".dstack/workflows/hello-cache.yaml"> 

```yaml
workflows:
  - name: hello-cache
    provider: code
    cache:
      - ~/.cache/pip
      - ./data
      - ./models
```

</div>

!!! info "NOTE:"
    Cache saves files in its own storage and downloads them at startup. This can
    improve performance and save on data transfer costs. 


#### Cleaning up the cache

To clean up the cache, you can delete the files directly from the dev environment or use the `dstack prune cache`
CLI command, followed by the name of the development environment.

[//]: # (TODO [MAJOR]: Cache is not the same as persistent storage)

[//]: # (TODO [TASK]: Elaborate on the main benefits of using dstack for dev environments)