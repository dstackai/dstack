# Volumes

Volumes allow you to persist data between runs. `dstack` supports two kinds of volumes: [network volumes](#network-volumes)
and [instance volumes](#instance-volumes).

## Network volumes

`dstack` allows to create and attach network volumes to dev environments, tasks, and services.

> Network volumes are currently supported with the `aws`, `gcp`, and `runpod` backends.
Support for other backends and SSH fleets is coming soon.

### Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `vol.dstack.yml`
are both acceptable).

<div editor-title="vol.dstack.yml"> 

```yaml
type: volume
# A name of the volume
name: my-new-volume

# Volumes are bound to a specific backend and region
backend: aws
region: eu-central-1

# Required size
size: 100GB
```

</div>

If you use this configuration, `dstack` will create a new volume based on the specified options.

!!! info "Registering existing volumes"
    If you prefer not to create a new volume but to reuse an existing one (e.g., created manually), you can 
    [specify its ID via `volume_id`](../reference/dstack.yml/volume.md#existing-volume). In this case, `dstack` will register the specified volume so that you can use it with dev environments, tasks, and services.

!!! info "Reference"
    See [.dstack.yml](../reference/dstack.yml/volume.md) for all the options supported by
    volumes, along with multiple examples.

### Create, register, or update a volume

To create or register the volume, simply call the `dstack apply` command:

<div class="termy">

```shell
$ dstack apply -f volume.dstack.yml
Volume my-new-volume does not exist yet. Create the volume? [y/n]: y

 NAME           BACKEND  REGION        STATUS     CREATED 
 my-new-volume  aws      eu-central-1  submitted  now     

```

</div>

> When creating the volume `dstack` automatically creates an `ext4` file system on it.

Once created, the volume can be attached with dev environments, tasks, and services.

### Attach a volume { #attach-network-volume }

Dev environments, tasks, and services let you attach any number of network volumes.
To attach a network volume, simply specify its name using the `volumes` property
and specify where to mount its contents:

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
# A name of the dev environment
name: vscode-vol

ide: vscode

# Map the name of the volume to any path 
volumes:
  - name: my-new-volume
    path: /volume_data

# You can also use the short syntax in the `name:path` form
# volumes:
#   - my-new-volume:/volume_data
```

</div>

Once you run this configuration, the contents of the volume will be attached to `/volume_data` inside the dev environment, 
and its contents will persist across runs.

!!! info "Attaching volumes across regions and backends"
    If you're unsure in advance which region or backend you'd like to use (or which is available),
    you can specify multiple volumes for the same path.

    <div editor-title=".dstack.yml">

    ```yaml
    volumes:
      - name: [my-aws-eu-west-1-volume, my-aws-us-east-1-volume]
        path: /volume_data
    ```

    </div>

    `dstack` will attach one of the volumes based on the region and backend of the run.  

??? info "Limitations"
    When you're running a dev environment, task, or service with `dstack`, it automatically mounts the project folder contents
    to `/workflow` (and sets that as the current working directory). Right now, `dstack` doesn't allow you to 
    attach volumes to `/workflow` or any of its subdirectories.

### Manage volumes { #manage-network-volumes }

#### List volumes

The [`dstack volume list`](../reference/cli/index.md#dstack-volume-list) command lists created and registered volumes:

```
$ dstack volume list
NAME            BACKEND  REGION        STATUS  CREATED
 my-new-volume  aws      eu-central-1  active  3 weeks ago
```

#### Delete volumes

When the volume isn't attached to any active dev environment, task, or service, you can delete it using `dstack delete`:

```shell
$ dstack delete -f vol.dstack.yaml
```

If the volume was created using `dstack`, it will be physically destroyed along with the data.
If you've registered an existing volume, it will be de-registered with `dstack` but will keep the data.

## Instance volumes

> Instance volumes are currently supported on all backends except `runpod`, `vastai` and `kubernetes`.

Unlike [network volumes](#network-volumes), which are persistent external resources mounted over network,
instance volumes are part of the instance storage. Basically, the instance volume is a filesystem path
(a directory or a file) mounted inside the run container.

As a consequence, the contents of the instance volume are specific to the instance
where the run is executed, and data persistence, integrity, and even existence are guaranteed only if the subsequent run
is executed on the same exact instance, and there is no other runs in between.

### Manage volumes { #manage-instance-volumes }

You don't need to create or delete instance volumes, and they are not displayed in the
[`dstack volume list`](../reference/cli/index.md#dstack-volume-list) command output.

### Attach a volume { #attach-instance-volume }

Dev environments, tasks, and services let you attach any number of instance volumes.
To attach an instance volume, specify the `instance_path` and `path` in the `volumes` property:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
# A name of the dev environment
name: vscode-vol

ide: vscode

# Map the instance path to any container path
volumes:
  - instance_path: /mnt/volume
    path: /volume_data

# You can also use the short syntax in the `instance_path:path` form
# volumes:
#   - /mnt/volume:/volume_data
```

</div>

### Use cases { #instance-volumes-use-cases }

Despite the limitations, instance volumes can still be useful in some cases:

=== "Cache"

    For example, if runs regularly install packages with `pip install`, include the instance volume in the run configuration
    to reuse pip cache between runs:

    <div editor-title=".dstack.yml">

    ```yaml
    type: task

    volumes:
      - /dstack-cache/pip:/root/.cache/pip
    ```

    </div>

=== "Network storage with SSH fleet"

    If you manage your own instances, you can mount network storages (e.g., NFS or SMB) to the hosts and access them in the runs.
    Imagine you mounted the same network storage to all the fleet instances using the same path `/mnt/nfs-storage`,
    then you can treat the instance volume as a shared persistent storage:

    <div editor-title=".dstack.yml">

    ```yaml
    type: task

    volumes:
      - /mnt/nfs-storage:/storage
    ```

    </div>

## FAQ

##### Can I use network volumes across backends?

Since volumes are backed up by cloud network disks, you can only use them within the same cloud. If you need to access
data across different backends, you should either use object storage or replicate the data across multiple volumes.

##### Can I use network volumes across regions?

Typically, network volumes are associated with specific regions, so you can't use them in other regions. Often,
volumes are also linked to availability zones, but some providers support volumes that can be used across different
availability zones within the same region.

If you don't want to limit a run to one particular region, you can create different volumes for different regions
and specify them for the same mount point as [documented above](#attach-network-volume).

##### Can I attach network volumes to multiple runs or instances?

You can mount a volume in multiple runs. This feature is currently supported only by the `runpod` backend.
