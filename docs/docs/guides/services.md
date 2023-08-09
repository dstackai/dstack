# Services

A service is an application that is accessible through a public endpoint managed by `dstack`.

Using `dstack`, you can define such a service through a configuration file and have it
automatically deployed in any cloud of your choice.

## Configuration

To configure a service, create its configuration file. It can be defined
in any folder but must be named with a suffix `.dstack.yml`.

Here's an example:

<div editor-title="serve.dstack.yml"> 

```yaml
type: service

gateway: ${{ secrets.GATEWAY_ADDRESS }}

port: 8000

commands:
  - python -m http.server 8000
```

</div>

For more details on the syntax of the `dstack.yml` file, refer to the [Reference](../reference/dstack.yml/service.md).

## Configuring a gateway

Before you can run a service, you have to configure a gateway.

First, you have to create a gateway in a project of your choice using the `dstack gateway create` command:

<div class="termy">

```shell
$ dstack gateway create

Creating gateway...

 NAME                        ADDRESS    
 dstack-gateway-fast-walrus  98.71.213.179 

```

</div>

!!! info "NOTE:"
    You can use the `--project` argument to indicate the project.
    Only AWS, GCP, and Azure projects allow creating gateways.

Once the gateway is up, go ahead and create a secret with the gateway's address.

<div class="termy">

```shell
$ dstack secrets add GATEWAY_ADDRESS 98.71.213.179
```
</div>

!!! info "NOTE:"
    You can use the `--project` argument to indicate the project.

    If you plan to run services in Lambda Cloud, you
    can use the gateway created in AWS, GCP, or Azure. Just make sure to create a secret in Lambda Cloud that
    references the correct gateway address.

For more details, check the [`dstack gateway`](../reference/cli/gateway.md) 
and [`dstack secrets`](../reference/cli/secrets.md) commands' reference pages.

## Running a service

To run a service, use the `dstack run` command followed by the path to the directory you want to use as the
working directory.

If your configuration file has a name different from `.dstack.yml`, pass the path to it using the `-f` argument.

<div class="termy">

```shell
$ dstack run . -f serve.dstack.yml

 RUN           CONFIGURATION     USER   PROJECT  INSTANCE  RESOURCES        SPOT
 yellow-cat-1  serve.dstack.yml  admin  local    -         5xCPUs, 15987MB  auto  

Provisioning...
---> 100%

Serving HTTP on http://98.71.213.179:80/ ...
```

</div>

This command deploys the service, and forwards the traffic to the gateway, 
providing you with a public endpoint.

??? info "Endpoint URL"
    By default, the public endpoint URL is `<gateway address>:80`. If you want to run multiple services on the same gateway,
    you have two options. You can either map a custom domain to the gateway address (and pass it to the secret), or you can
    configure a custom port mapping in YAML (instead of `8000`, specify `<gateway port>:8000`).

??? info "Using .gitignore"
    When running a service, `dstack` uses the exact version of code that is present in the folder where you
    use the `dstack run` command.

    If your folder has large files or folders, this may affect the performance of the `dstack run` command. To avoid this,
    make sure to create a `.gitignore` file and include these large files or folders that you don't want to include when
    running dev environments or tasks.

For more details on the `dstack run` command, refer to the [Reference](../reference/cli/run.md).

## Profiles

If you [configured](../projects.md) a project that uses a cloud backend, you can define profiles that specify the
project and the cloud resources to be used.

To configure a profile, simply create the `profiles.yml` file in the `.dstack` folder within your project directory. 
Here's an example:

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: gcp-large
    project: gcp
    
    resources:
      memory: 24GB
      gpu:
        memory: 48GB
        
    spot_policy: auto
      
    default: true
```

</div>

!!! info "Using spot instances"
    If `spot_policy` is set to `auto`, `dstack` prioritizes spot instances.
    If these are unavailable, it uses `on-demand` instances. To cut costs, set `spot_policy` to `spot`.

By default, the `dstack run` command uses the default profile.

!!! info "Multiple profiles"
    You can define multiple profiles according to your needs and use any of them with the `dstack run` command by specifying
    the desired profile using the `--profile` argument.

For more details on the syntax of the `profiles.yml` file, refer to the [Reference](../reference/profiles.yml.md).