# `gateway`

The `gateway` configuration type allows creating and updating [gateways](../../concepts/gateways.md).

## Root reference

#SCHEMA# dstack._internal.core.models.gateways.GatewayConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `certificate`

=== "Let's encrypt"

    #SCHEMA# dstack._internal.core.models.gateways.LetsEncryptGatewayCertificate
        overrides:
          show_root_heading: false
          type:
            required: true

=== "ACM" 

    #SCHEMA# dstack._internal.core.models.gateways.ACMGatewayCertificate
        overrides:
          show_root_heading: false
          type:
            required: true

## Examples

### Creating a new gateway { #new-gateway }

<div editor-title="gateway.dstack.yml"> 

```yaml
type: gateway
# A name of the gateway
name: example-gateway

# Gateways are bound to a specific backend and region
backend: aws
region: eu-west-1

# This domain will be used to access the endpoint
domain: example.com
```

</div>

[//]: # (TODO: other examples, e.g. private 