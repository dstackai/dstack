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

gateway: ${{ secrets.GATEWAY_ADDRESS }}

port: 7860

python: "3.11" # (Optional) If not specified, your local version is used.

commands:
  - pip install -r requirements
  - python app.py
```

</div>

Before running a service, you need to configure a gateway address to run the service on.

??? info "Gateway"

    ### Configure a gateway address 

    First, you have to create a gateway in one of the clouds of your choice.
    
    <div class="termy">
    
    ```shell
    $ dstack gateway create --backend aws
    
    Creating gateway...
    
     BACKEND  NAME                        ADDRESS    
     aws      dstack-gateway-fast-walrus  98.71.213.179  
    ```
    
    </div>

    Once the gateway is up, create a secret with the gateway's address.
    
    <div class="termy">
    
    ```shell
    $ dstack secrets add GATEWAY_ADDRESS 98.71.213.179
    ```
    </div>
    
    ### Configure a domain and enable HTTPS (optional)
    
    By default, if you run the service, it will be available at `http://<gateway address>`.
    
    If you wish to enable HTTPS and run multiple services on the same gateway, the best approach is to configure a wildcard
    domain.

    To do this, go to your domain provider, and create a wildcard `A` DNS record (e.g. `*.mydomain.com`) pointing to the 
    address of the gateway (e.g. `98.71.213.179`).
     
    Now, replace the value of the `GATEWAY_ADDRESS` secret with the subdomain to which you want to deploy your service.
    
    <div class="termy">
    
    ```shell
    $ dstack secrets add GATEWAY_ADDRESS `myservice.mydomain.com`
    ```
    </div>
    
    If you are using a domain name as the gateway address for your service, dstack enables HTTPS automatically using [Let's
    Encrypt](https://letsencrypt.org/).
    
    For more details on the [`dstack gateway`](../reference/cli/gateway.md) and [`dstack secrets`](../reference/cli/secrets.md) 
    commands, refer to their reference pages.

### Configure the environment

By default, `dstack` uses its own Docker images to run services, which are pre-configured with Python, Conda, and essential CUDA drivers.

You can install packages using `pip` and `conda` executables from `commands`.

??? info "Docker image"
    If you prefer to use your custom Docker image, use the `image` property in the configuration.

    <div editor-title="serve.dstack.yml">

    ```yaml
    type: service

    gateway: ${{ secrets.GATEWAY_ADDRESS }}
    
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

    gateway: ${{ secrets.GATEWAY_ADDRESS }}
    
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

The `.dstack.yml` has many other properties. To view them all, refer to the [Reference](../reference/dstack.yml/service.md).

## Run the configuration

To run a service, use the `dstack run` command followed by the path to the directory you want to use as the
working directory.

If the configuration file is named other than `.dstack.yml`, pass its path via the `-f` argument.

<div class="termy">

```shell
$ dstack run . -f serve.dstack.yml

 RUN           CONFIGURATION     USER   BACKEND  INSTANCE  RESOURCES        SPOT
 yellow-cat-1  serve.dstack.yml  admin  aws      -         5xCPUs, 15987MB  auto  

Provisioning...
---> 100%

Serving HTTP on https://myservice.mydomain.com ...
```

</div>

This command deploys the service, and forwards the traffic to the gateway address.

### Configure resources, price, etc

For every run, you can specify hardware resources like memory and GPU, along with various run policies (e.g., maximum
hourly price, use of spot instances, etc.).

| Example                     | Description                                |
|-----------------------------|--------------------------------------------|
| `dstack run . --gpu A10`    | Use an instance with `NVIDIA A10` GPU      |
| `dstack run . --gpu A100:8` | Use an instance with 8 `NVIDIA A100` GPUs  |
| `dstack run . --gpu 24GB`   | Use an instance with a GPU that has `24GB` |

The `dstack run` command has many options. To view them, refer to the [Reference](../reference/cli/run.md).

??? info "Profiles"
    ### Configure profiles (optional) 

    Instead of configuring resources, price, and policies through `dstack run`, you can use profiles. To set up a profile, 
    create the `.dstack/profiles.yml` file in the root folder of the project. 
    
    <div editor-title=".dstack/profiles.yml"> 
    
    ```yaml
    profiles:
      - name: large

        resources:
          memory: 24GB  # (Optional) The minimum amount of RAM memory
          gpu:
            memory: 48GB  # (Optional) The minimum amount of GPU memory 
            
        max_price: 1.5 # (Optional) The maximim price per instance, in dollards.

        max_duration: 1d # (Optional) The maximum duration of the run.

        spot_policy: auto # (Optional) The spot policy. Supports `spot`, `on-demand, and `auto`.

        backends: [azure, lambda]  # (Optional) Use only listed backends 

        default: true # (Optional)
    ```
    
    </div>

    #### Spot instances

    If `spot_policy` is set to `auto`, `dstack` gives priority to spot instances. If unavailable, it uses on-demand instances. 
    To reduce costs, set `spot_policy` to `spot`. Keep in mind that spot instances are much cheaper but may be interrupted. 
    Your code should handle interruptions and resume from saved checkpoints.

    #### Default profile
    
    By default, the `dstack run` command uses the default profile. You 
    can override it by passing the `--profile` argument to the `dstack run` command.
    
    For more details on the syntax of the `profiles.yml` file, refer to the [Reference](../reference/profiles.yml.md).