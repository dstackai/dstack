# Services

A service is an application that is accessible through a public endpoint.

Using `dstack`, you can define such a service through a configuration file and run it on the
configured clouds that offer the best price and availability.

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

Before running a service, you need to configure a gateway address to run the service on.

??? info "Gateway"

    ### Configure a gateway 

    First, you have to create a gateway in one of the clouds of your choice.
    
    <div class="termy">
    
    ```shell
    $ dstack gateway create --backend aws
    
    Creating gateway...
    
     BACKEND  NAME                        ADDRESS    
     aws      dstack-gateway-fast-walrus  98.71.213.179  
    ```
    
    </div>

    Once the gateway is up, it will be used as default by all services in the project.

    ### Configure a domain and enable HTTPS (optional)
    
    By default, if you run the service, it will be available at `http://<gateway ip address>`.
    
    If you wish to enable HTTPS and run multiple services on the same gateway, the best approach is to configure a wildcard
    domain.

    To do this, go to your domain provider, and create a wildcard `A` DNS record (e.g. `*.mydomain.com`) pointing to the 
    address of the gateway (e.g. `98.71.213.179`).
     
    Now, edit the gateway and add the wildcard domain in the project settings.
    
    If you are using a wildcard domain with the gateway, dstack picks a random subdomain and enables HTTPS automatically using [Let's
    Encrypt](https://letsencrypt.org/).
    
    For more details on the [`dstack gateway`](../reference/cli/gateway.md).

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

This command deploys the service, and forwards the traffic to the gateway address.

### Requesting resources

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
