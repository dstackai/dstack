# Quickstart

`dstack` is an open-source tool that enables the execution of LLM workloads across multiple cloud GPU providers, ensuring
optimal GPU pricing and availability.

## Installation

To use `dstack`, install it with `pip`, and start the server.

<div class="termy">

```shell
$ pip install "dstack[aws,gcp,azure,lambda]"
$ dstack start

The server is available at http://127.0.0.1:3000?token=b934d226-e24a-4eab-eb92b353b10f
```

</div>

## Configure clouds

Upon startup, the server sets up the default project called `main`.
Prior to using `dstack`, make sure to [configure clouds](guides/clouds.md#configuring-backends).

[//]: # (![]&#40;../assets/images/dstack-hub-view-project-empty.png&#41;{ width=800 })

[//]: # (Once cloud backends are configured, `dstack` will be able to provision cloud resources across configured clouds, ensuring)
[//]: # (the best price and higher availability.)

## Initialize the repo

To use `dstack` for your project, make sure to first run the [`dstack init`](reference/cli/init.md) command in the root folder of the project.

<div class="termy">

```shell
$ mkdir quickstart && cd quickstart
$ dstack init
```

</div>

## Define a configuration

A configuration is a YAML file that describes what you want to run with `dstack`. Configurations can be of three
types: `dev-environment`, `task`, and `service`.

### Dev environments

A dev environment is a virtual machine pre-configured an IDE.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

python: "3.11" # (Optional) If not specified, your local version is used

setup: # (Optional) Executed once at the first startup
  - pip install -r requirements.txt

ide: vscode
```

</div>

Once it's live, you can open it in your local VS Code by clicking the provided URL in the output.

### Tasks

A task can be any script that you may want to run on demand: a batch job, or a web application.

<div editor-title="serve.dstack.yml"> 

```yaml
type: task

python: "3.11" # (Optional) If not specified, your local version is used

ports:
  - 7860

commands:
  - pip install -r requirements.txt
  - python app.py
```

</div>

While the task runs in the cloud, the CLI forwards traffic, allowing you to access the application from your local
machine. 

### Services

A service is an application that is accessible through a public endpoint.

<div editor-title="deploy.dstack.yml"> 

```yaml
type: service

python: "3.11" # (Optional) If not specified, your local version is used

gateway: ${{ secrets.GATEWAY_ADDRESS }}

port: 7860

commands:
  - pip install -r requirements.txt
  - python app.py
```

</div>

Once the service is up, `dstack` makes it accessible from the Internet through
the [gateway](guides/services.md#configure-a-gateway-address).

[//]: # (!!! info "Configuration filename")
[//]: # (    The configuration file must be named with the suffix `.dstack.yml`. For example,)
[//]: # (    you can name the configuration file `.dstack.yml` or `serve.dstack.yml`. You can define)
[//]: # (    these configurations anywhere within your project. )
[//]: # (    )
[//]: # (    Each folder may have one default configuration file named `.dstack.yml`.)

For more details on the file syntax, refer to [`.dstack.yml`](../docs/reference/dstack.yml/index.md).

## Run the configuration

### Default configurations

To run a configuration, you have to call the [`dstack run`](reference/cli/run.md) command and pass the path to the 
directory which you want to use as a working directory when running the configuration.

<div class="termy">

```shell
$ dstack run . 

 RUN          CONFIGURATION  BACKEND  RESOURCES        SPOT  PRICE
 fast-moth-1  .dstack.yml    aws      5xCPUs, 15987MB  yes   $0.0547


Provisioning and starting SSH tunnel...
---> 100%

To open in VS Code Desktop, use this link:
  vscode://vscode-remote/ssh-remote+fast-moth-1/workflow
```

</div>

If you've not specified a specific configuration file, `dstack` will use the default configuration
defined in the given directory (named `.dstack.yml`).

### Non-default configurations

If you want to run a non-default configuration, you have to specify the path to the configuration
using the `-f` argument:

<div class="termy">

```shell
$ dstack run . -f serve.dstack.yml

 RUN             CONFIGURATION     BACKEND  RESOURCES        SPOT  PRICE
 old-lionfish-1  serve.dstack.yml  aws      5xCPUs, 15987MB  yes   $0.0547

Provisioning and starting SSH tunnel...
---> 100%

Launching in *reload mode* on: http://127.0.0.1:7860 (Press CTRL+C to quit)
```

</div>

[//]: # (!!! info "Port forwarding")
[//]: # (    By default, `dstack` forwards the ports used by dev environments and tasks to your local machine for convenient access.)

For more details on the run command, refer to [`dstack run`](reference/cli/run.md).

### Requesting resources

You can request resources using the [`--gpu`](reference/cli/run.md#GPU) 
and [`--memory`](reference/cli/run.md#MEMORY) arguments with `dstack run`, 
or through [`resources`](reference/profiles.yml.md#RESOURCES) with `.dstack/profiles.yml`.

Both the [`dstack run`](reference/cli/run.md) command and [`.dstack/profiles.yml`](reference/profiles.yml.md)
support various other options, including requesting spot instances, defining the maximum run duration or price, and
more.

!!! info "Automatic instance discovery"
    `dstack` will automatically select the suitable instance type from a cloud provider and region with the best
    price and availability.