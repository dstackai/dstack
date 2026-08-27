# `gateway`

The `gateway` configuration type allows creating and updating [gateways](../../concepts/gateways.md).

## Root reference

#SCHEMA# dstack._internal.core.models.gateways.GatewayConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `certificate`

Set to `null` to disable certificates (e.g. for [private gateways](../../concepts/gateways.md#public-ip)).

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

### `load_balancer`

=== "ALB"

    #SCHEMA# dstack._internal.core.models.gateways.ALBGatewayLoadBalancer
        overrides:
          show_root_heading: false
          type:
            required: true
