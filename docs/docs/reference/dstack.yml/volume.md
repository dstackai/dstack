# volume

The `volume` configuration type allows creating and updating volumes.

!!! info "Filename"
    Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `volume.dstack.yml` are both acceptable)
    and can be located in the project's root directory or any nested folder.
    Any configuration can be applied via [`dstack apply`](../cli/index.md#dstack-apply).

## Examples

### AWS EBS volume

<div editor-title="aws-volume.dstack.yml"> 

```yaml
type: volume
name: my-aws-volume
backend: aws
region: eu-central-1
size: 100GB
```

</div>


### AWS EBS external volume

<div editor-title="aws-ext-volume.dstack.yml"> 

```yaml
type: volume
name: my-ext-aws-volume
backend: aws
region: eu-central-1
volume_id: vol-123456
```

</div>


## Root reference

#SCHEMA# dstack._internal.core.models.volumes.VolumeConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true
