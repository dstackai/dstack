# Services

A service is a web app accessible from the Internet. It is ideal for deploying wep apps 
for production purposes.

## Using the CLI

### Set up a gateway

Before you can run a service, you need to set up a gateway. To do that, you'll need your own domain.

#### Create a gateway

For example, if your domain is `example.com`, go ahead and run the 
`dstack gateway create` command:

<div class="termy">
   
```shell
$ dstack gateway create --domain example.com --region eu-west-1 --backend aws

Creating gateway...
---> 100%

 BACKEND  REGION     NAME          ADDRESS        DOMAIN       DEFAULT
 aws      eu-west-1  sour-fireant  52.148.254.14  example.com  ✓
```

</div>

Afterward, in your domain's DNS settings, add an `A` DNS record for `*.example.com` 
pointing to the IP address of the gateway.

The gateway will take care of everything to make services available
from the Internet.
For instance, running a service will make it available at 
`https://<run-name>.example.com`.

### Define a configuration

To run a service via the CLI, first create its configuration file. 
The configuration file name must end with `.dstack.yml` (e.g., `.dstack.yml` or `dev.dstack.yml` are both acceptable).

<div editor-title="service.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest

env: 
  - MODEL_ID=TheBloke/Llama-2-13B-chat-GPTQ 

port: 80

commands:
  - text-generation-launcher --hostname 0.0.0.0 --port 80 --trust-remote-code
```

</div>

By default, `dstack` uses its own Docker images to run dev environments, 
which are pre-configured with Python, Conda, and essential CUDA drivers.

!!! info "Configuration options"
    Configuration file allows you to specify a custom Docker image, ports, environment variables, and many other 
    options.
    For more details, refer to the [Reference](../reference/dstack.yml/service.md).

### Run the configuration

The `dstack run` command requires the working directory path, and optionally, the `-f`
argument pointing to the configuration file.

If the `-f` argument is not specified, `dstack` looks for the default configuration (`.dstack.yml`) in the working directory.

<div class="termy">

```shell
$ dstack run . -f service.dstack.yml --gpu A100

 RUN           CONFIGURATION       BACKEND  RESOURCES        SPOT  PRICE
 yellow-cat-1  service.dstack.yml  aws      5xCPUs, 15987MB  yes   $0.0547  

Provisioning...
---> 100%

Serving HTTP on https://yellow-cat-1.example.com ...
```

</div>

#### Request resources

The `dstack run` command allows you to use `--gpu` to request GPUs (e.g. `--gpu A100` or `--gpu 80GB` or `--gpu A100:4`, etc.),
`--memory` to request memory (e.g. `--memory 128GB`),
and many other options (incl. spot instances, max price, max duration, etc.).

For more details on the `dstack run` command, refer to the [Reference](../reference/cli/run.md).

[//]: # (TODO: Example)