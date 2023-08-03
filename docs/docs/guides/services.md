# Services

A service is an application accessible from the global internet through the gateway.
Both cloud and local backends (behind NAT) could serve these applications.

## Gateways

To deploy service you need a gateway — small CPU instance with public IP address and, possibly, a domain.
Currently, dstack supports AWS, Azure, and GCP backend for gateway creation.
Use command bellow to create your first gateway.

```shell
$ dstack gateway create --project azure

Creating gateway, it may take some time...
 NAME                        ADDRESS    
 dstack-gateway-fast-walrus  23.100.30.60 

```

Now you could use this gateway for services in any project configured in the same hub,
regardless of backend type.

Use `dstack gateway list` to view gateways in the project. Use `dstack gateway delete` to free resources.

## Configuring a service

Create a service configuration, declaring gateway hostname and application port.

```yaml
type: service
gateway: 23.100.30.60
port: 8000
commands:
  - python -m http.server 8000
```

If you wouldn't like to put hostname directly to a configuration file, you could use secrets interpolation.
Firstly, create secret in the project, where you are going to run your service.

```shell
$ dstack secrets add GATEWAY_IP 23.100.30.60 --project local
```

Secondly, replace gateway hostname with a variable.

```yaml
type: service
gateway: ${{ secrets.GATEWAY_IP }}
port: 8000
commands:
  - python -m http.server 8000
```

By default, the service would be available on port 80, but you could configure a mapping, e.g. to port 5001.

```yaml
type: service
gateway: ${{ secrets.GATEWAY_IP }}
port: "5001:8000"
commands:
  - python -m http.server 8000
```

## Running a service

To run a service use command below.

```shell
$ dstack run . -f service.dstack.yml --project local
```

The service would be available at `http://23.100.30.60:5001`.


## Running multiple services through the same gateway

You can't run multiple services at the same gateway hostname and external port.
As soon as service is down, you could reuse the same gateway hostname and external port.

If you would like to run multiple services, there are two possible solutions:

- Use different ports
- Use different domains

Add DNS record for your domain, pointing to the gateway IP address.
After that you could use this domain name as a gateway hostname alias.
