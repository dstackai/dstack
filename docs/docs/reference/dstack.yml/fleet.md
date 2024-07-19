# fleet

The `fleet` configuration type allows creating and updating fleets.

> Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `fleet.dstack.yml` are both acceptable)
> and can be located in the project's root directory or any nested folder.
> Any configuration can be applied via [`dstack apply`](../cli/index.md#dstack-apply).

## Examples

### Creating a cloud fleet { #create-cloud-fleet }

<div editor-title="gcp-fleet.dstack.yml"> 

```yaml
type: fleet
name: my-gcp-fleet
nodes: 4
placement: cluster
backends: [gcp]
resources:
  gpu: 1
```

</div>

### Creating an on-prem fleet { #create-ssh-fleet }

<div editor-title="ssh-fleet.dstack.yml"> 
    
```yaml
type: fleet
name: my-ssh-fleet
ssh:
  user: ubuntu
  ssh_key_path: ~/.ssh/key.pem
  hosts:
    - "3.255.177.51"
    - "3.255.177.52"
```

</div>


## Root reference

#SCHEMA# dstack._internal.core.models.fleets.FleetConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

## `ssh`

#SCHEMA# dstack._internal.core.models.fleets.SSHParams
    overrides:
      show_root_heading: false


## `ssh.hosts[n]`

#SCHEMA# dstack._internal.core.models.fleets.SSHHostParams
    overrides:
      show_root_heading: false

## `resources`

#SCHEMA# dstack._internal.core.models.resources.ResourcesSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true
      item_id_prefix: resources-

## `resouces.gpu` { #resources-gpu data-toc-label="resources.gpu" } 

#SCHEMA# dstack._internal.core.models.resources.GPUSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

## `resouces.disk` { #resources-disk data-toc-label="resources.disk" }

#SCHEMA# dstack._internal.core.models.resources.DiskSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

## `retry`

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetry
    overrides:
      show_root_heading: false
