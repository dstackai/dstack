# volume

The `volume` configuration type allows creating, registering, and updating volumes.

> Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `vol.dstack.yml` are both acceptable)
> and can be located in the project's root directory or any nested folder.
> Any configuration can be applied via [`dstack apply`](../cli/index.md#dstack-apply).

## Examples

### Creating a new volume { #create-volume }

<div editor-title="vol.dstack.yml"> 

```yaml
type: volume
name: my-aws-volume
backend: aws
region: eu-central-1
size: 100GB
```

</div>

### Registering an existing volume { #register-volume }

<div editor-title="ext-vol.dstack.yml"> 
    
```yaml
type: volume
name: my-external-volume
backend: aws
region: eu-central-1
volume_id: vol1235
```

</div>


## Root reference

#SCHEMA# dstack._internal.core.models.volumes.VolumeConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true
