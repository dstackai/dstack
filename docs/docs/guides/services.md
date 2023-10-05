# Services

A service in `dstack` is a web app accessible through a public endpoint. When running a web app as a service,
`dstack` automatically creates a public endpoint, enabling you to use your domain and HTTPS.

!!! info "NOTE:"
    Services are ideal for deploying wep apps (e.g., LLMs) for production purposes.
    If you intend to run a web app for development purposes, please refer to [tasks](tasks.md).

## Define a configuration

To configure a service, create its configuration file. It can be defined
in any folder but must be named with a suffix `.dstack.yml`.

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

port: 7860

python: "3.11" # (Optional) If not specified, your local version is used.

commands:
  - pip install -r requirements
  - python app.py
```

</div>

### Configure the environment

By default, `dstack` uses its own Docker images to run services, which are pre-configured with Python, Conda, and essential CUDA drivers.

You can install packages using `pip` and `conda` executables from `commands`.

??? info "Docker image"
    If you prefer to use your custom Docker image, use the `image` property in the configuration.

    <div editor-title="serve.dstack.yml">

    ```yaml
    type: service

    port: 7860
    
    image: nvcr.io/nvidia/pytorch:22.12-py3
    
    commands:
      - pip install -r requirements.txt
      - python app.py
    ```

    </div>

??? info "Build command (experimental)" 

    In case you'd like to pre-build the environment rather than install packaged on every run,
    you can use the `build` property. Here's an example:
    
    <div editor-title="serve.dstack.yml"> 
    
    ```yaml
    type: service

    port: 7860

    python: "3.11" # (Optional) If not specified, your local version is used.
    
    build:
      - pip install -r requirements.txt
    
    commands:
      - python app.py
    ```
    
    </div>

    In this case, you have to pass `--build` to `dstack run`.

    <div class="termy">
    
    ```shell
    $ dstack run . -f serve.dstack.yml --build
    ```
    
    </div>

    If there is no pre-built image, the `dstack run` command will build it and upload it to the storage. If the pre-built
    image is already available, the `dstack run` command will reuse it.

For more details on the file syntax, refer to [`.dstack.yml`](../reference/dstack.yml/service.md).

## Run the configuration

!!! info "Gateway"
    Before running a service, ensure that you have configured a [gateway](clouds.md#configure-gateways).

To run a service, use the `dstack run` command followed by the path to the directory you want to use as the
working directory.

If the configuration file is named other than `.dstack.yml`, pass its path via the `-f` argument.

<div class="termy">

```shell
$ dstack run . -f serve.dstack.yml

 RUN           CONFIGURATION     BACKEND  RESOURCES        SPOT  PRICE
 yellow-cat-1  serve.dstack.yml  aws      5xCPUs, 15987MB  yes  $0.0547  

Provisioning...
---> 100%

Serving HTTP on https://yellow-cat-1.mydomain.com ...
```

</div>

This command deploys the service, and forwards the traffic to the gateway's endpoint.

!!! info "Wildcard domain"
    If you've configured a [wildcard domain](clouds.md#configure-gateways) for the gateway, 
    `dstack` enables HTTPS automatically and serves the service at 
    `https://<run name>.<your domain name>`.

    If you wish to customize the run name, you can use the `-n` argument with the `dstack run` command. 

### Request resources

You can request resources using the [`--gpu`](../reference/cli/run.md#GPU) 
and [`--memory`](../reference/cli/run.md#MEMORY) arguments with `dstack run`, 
or through [`resources`](../reference/profiles.yml.md#RESOURCES) with `.dstack/profiles.yml`.

Both the [`dstack run`](../reference/cli/run.md) command and [`.dstack/profiles.yml`](../reference/profiles.yml.md)
support various other options, including requesting spot instances, defining the maximum run duration or price, and
more.

!!! info "Automatic instance discovery"
    `dstack` will automatically select the suitable instance type from a cloud provider and region with the best
    price and availability.

For more details on the run command, refer to [`dstack run`](../reference/cli/run.md).