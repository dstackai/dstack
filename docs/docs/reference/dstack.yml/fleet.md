# fleet

The `fleet` configuration type allows creating and updating fleets.

> Configuration files must be inside the project repo, and their names must end with `.dstack.yml` 
> (e.g. `.dstack.yml` or `fleet.dstack.yml` are both acceptable).
> Any configuration can be run via [`dstack apply`](../cli/index.md#dstack-apply).

## Examples

### Cloud

<div editor-title="fleet-distrib.dstack.yml"> 

```yaml
type: fleet
# The name is optional, if not specified, generated randomly
name: my-fleet

# The number of instances
nodes: 4
# Ensure the instances are interconnected
placement: cluster

# Uncomment to leverage spot instances
#spot_policy: auto

resources:
  gpu:
    # 24GB or more vRAM
    memory: 24GB..
    # One or more GPU
    count: 1..
```

</div>

### SSH

<div editor-title="fleet-ssh.dstack.yml"> 
    
```yaml
type: fleet
# The name is optional, if not specified, generated randomly
name: my-ssh-fleet

# Ensure instances are interconnected
placement: cluster

# The user, private SSH key, and hostnames of the on-prem servers
ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/id_rsa
  hosts:
    - 3.255.177.51
    - 3.255.177.52
```

</div>

[//]: # (TODO: a cluster, individual user and identity file, etc)

[//]: # (TODO: other examples, for all properties like in dev-environment/task/service)

## Root reference

#SCHEMA# dstack._internal.core.models.fleets.FleetConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

## `ssh_config`

#SCHEMA# dstack._internal.core.models.fleets.SSHParams
    overrides:
      show_root_heading: false

## `ssh_config.hosts[n]`

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
