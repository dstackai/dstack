# volume

The `volume` configuration type allows creating, registering, and updating volumes.

> Configuration files must be inside the project repo, and their names must end with `.dstack.yml` 
> (e.g. `.dstack.yml` or `fleet.dstack.yml` are both acceptable).
> Any configuration can be run via [`dstack apply`](../cli/index.md#dstack-apply).

## Examples

### Creating a new volume { #new-volume }

<div editor-title="vol.dstack.yml"> 

```yaml
type: volume
# The name of the volume
name: my-new-volume

# Volumes are bound to a specific backend and region
backend: aws
region: eu-central-1

# The size of the volume
size: 100GB
```

</div>

### Registering an existing volume { #existing-volume }

<div editor-title="vol-exist.dstack.yml"> 
    
```yaml
type: volume
# The name of the volume
name: my-existing-volume

# Volumes are bound to a specific backend and region
backend: aws
region: eu-central-1

# The ID of the volume in AWS
volume_id: vol1235
```

</div>


## Root reference

#SCHEMA# dstack._internal.core.models.volumes.VolumeConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true
