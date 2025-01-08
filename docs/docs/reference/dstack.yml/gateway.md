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
