# gateway

The `gateway` configuration type allows creating and updating [gateways](../../services.md).

> Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `gateway.dstack.yml` are both acceptable)
> and can be located in the project's root directory or any nested folder.
> Any configuration can be applied via [`dstack apply`](../cli/index.md#dstack-apply).

## Examples

<div editor-title="gateway.dstack.yml"> 

```yaml
type: gateway
name: example-gateway

backend: aws
region: eu-west-1
domain: example.com
```

</div>


## Root reference

#SCHEMA# dstack._internal.core.models.gateways.GatewayConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

## `certificate[type=lets-encrypt]`

#SCHEMA# dstack._internal.core.models.gateways.LetsEncryptGatewayCertificate
    overrides:
      show_root_heading: false
      type:
        required: true

## `certificate[type=acm]`

#SCHEMA# dstack._internal.core.models.gateways.ACMGatewayCertificate
    overrides:
      show_root_heading: false
      type:
        required: true
