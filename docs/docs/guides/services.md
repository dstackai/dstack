# Services

A service is an internet-accessible application accessed through a gateway.
These applications can be hosted on both cloud and local backends (behind NAT).

## Gateways

To deploy a service, you require a gateway: a small CPU instance with a public IP address and potentially a domain.
Currently, dstack supports AWS, Azure, and GCP backends for creating gateways.
Run the following command to create your first gateway:

```shell
$ dstack gateway create --project azure

Creating gateway, it may take some time...
 NAME                        ADDRESS    
 dstack-gateway-fast-walrus  23.100.30.60 
```

You can then use this gateway for services within any project configured on the same hub,
irrespective of the backend type.
Run `dstack gateway list` to view gateways within the project and `dstack gateway delete` to free up resources.

## Configuring Services

Construct a service configuration by specifying the gateway hostname and application port in a YAML format:

```yaml
type: service
gateway: 23.100.30.60
port: 8000
commands:
  - python -m http.server 8000
```

To avoid directly inputting the hostname in the configuration file, you can use secret interpolation.
Begin by creating a secret in the project where your service will run:

```shell
$ dstack secrets add GATEWAY_IP 23.100.30.60 --project local
```

Then replace the gateway hostname with a variable:

```yaml
type: service
gateway: ${{ secrets.GATEWAY_IP }}
port: 8000
commands:
  - python -m http.server 8000
```

The default service port is 80, but you can configure a mapping, such as to port 5001:

```yaml
type: service
gateway: ${{ secrets.GATEWAY_IP }}
port: "5001:8000"
commands:
  - python -m http.server 8000
```

## Running Services

Execute the following command to run a service:

```shell
$ dstack run . -f service.dstack.yml --project local
```

The service will be accessible at `http://23.100.30.60:5001`.

## Running Multiple Services via the Same Gateway

Running multiple services with the same gateway hostname and external port simultaneously is not possible.
However, you can reuse the same gateway hostname and external port if a service is no longer active.
If you wish to run multiple services, consider these two solutions:

- Utilize different ports
- Use distinct domains

Create a DNS record for your domain, pointing it to the gateway's IP address.
Following this, you can use the domain name as an alias for the gateway hostname.
