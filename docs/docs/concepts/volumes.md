# Volumes

Volumes enable data persistence between runs of dev environments, tasks, and services. 

`dstack` supports two kinds of volumes: 

* [Network volumes](#network-volumes) &mdash; provisioned via backends and mounted to specific container directories.
  Ideal for persistent storage.
* [Instance volumes](#instance-volumes) &mdash; bind directories on the host instance to container directories.
Useful as a cache for cloud fleets or for persistent storage with SSH fleets.

## Network volumes

Network volumes are currently supported for the `aws`, `gcp`, and `runpod` backends.

### Apply a configuration

First, define a volume configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `volume.dstack.yml` are both acceptable).

<div editor-title="volume.dstack.yml"> 

```yaml
type: volume
# A name of the volume
name: my-volume

# Volumes are bound to a specific backend and region
backend: aws
region: eu-central-1

# Required size
size: 100GB
```

</div>

If you use this configuration, `dstack` will create a new volume based on the specified options.

To create, update, or register the volume, pass the volume configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f volume.dstack.yml
Volume my-volume does not exist yet. Create the volume? [y/n]: y

 NAME       BACKEND  REGION        STATUS     CREATED 
 my-volume  aws      eu-central-1  submitted  now     

```

</div>


Once created, the volume can be attached to dev environments, tasks, and services.

> When creating a new network volume, `dstack` automatically creates an `ext4` filesystem on it.

??? info "Register existing volumes"
    If you prefer not to create a new volume but to reuse an existing one (e.g., created manually), you can 
    specify its ID via [`volume_id`](../reference/dstack.yml/volume.md#volume_id). In this case, `dstack` will register the specified volume so that you can use it with dev environments, tasks, and services.

    <div editor-title="volume.dstack.yml"> 

    ```yaml
    type: volume
    # The name of the volume
    name: my-volume
    
    # Volumes are bound to a specific backend and region
    backend: aws
    region: eu-central-1
    
    # The ID of the volume in AWS
    volume_id: vol1235
    ```
    
    </div>

    !!! info "Filesystem"
        If you register an existing volume, you must ensure the volume already has a filesystem.

!!! info "Reference"
    For all volume configuration options, refer to the [reference](../reference/dstack.yml/volume.md).

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
  - name: my-volume
    path: /volume_data

# You can also use the short syntax in the `name:path` form
# volumes:
#   - my-volume:/volume_data
```

</div>

Once you run this configuration, the contents of the volume will be attached to `/volume_data` inside the dev environment, 
and its contents will persist across runs.

??? info "Multiple regions or backends"
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

??? info "Distributed tasks"
    When using single-attach volumes such as AWS EBS with distributed tasks,
    you can attach different volumes to different nodes using `dstack` variable interpolation:

    <div editor-title=".dstack.yml">

    ```yaml
    type: task
    nodes: 8
    commands:
      - ...
    volumes:
      - name: data-volume-${{ dstack.node_rank }}
        path: /volume_data
    ```

    </div>

    This way, every node will use its own volume.

    Tip: To create volumes for all nodes using one volume configuration, specify volume name with `-n`:

    ```shell
    $ for i in {0..7}; do dstack apply -f vol.dstack.yml -n data-volume-$i -y; done
    ```

### Detach a volume { #detach-network-volume }

`dstack` automatically detaches volumes from instances when a run stops.

!!! info "Force detach"
    In some clouds such as AWS a volume may stuck in the detaching state.
    To fix this, you can abort the run, and `dstack` will force detach the volume.
    `dstack` will also force detach the stuck volume automatically after `stop_duration`.
    
    Note that force detaching a volume is a last resort measure and may corrupt the file system.
    Contact your cloud support if you experience volumes getting stuck in the detaching state.

### Manage volumes { #manage-network-volumes }

#### List volumes

The [`dstack volume list`](../reference/cli/dstack/volume.md#dstack-volume-list) command lists created and registered volumes:

<div class="termy">

```shell
$ dstack volume list
NAME        BACKEND  REGION        STATUS  CREATED
 my-volume  aws      eu-central-1  active  3 weeks ago
```

</div>

#### Delete volumes

When the volume isn't attached to any active dev environment, task, or service,
you can delete it by passing the volume configuration to `dstack delete`:

<div class="termy">

```shell
$ dstack delete -f vol.dstack.yaml
```

</div>

Alternatively, you can delete a volume by passing the volume name  to `dstack volume delete`.

If the volume was created using `dstack`, it will be physically destroyed along with the data.
If you've registered an existing volume, it will be de-registered with `dstack` but will keep the data.

### FAQs

??? info "Can I use network volumes across backends?"

    Since volumes are backed up by cloud network disks, you can only use them within the same cloud. If you need to access
    data across different backends, you should either use object storage or replicate the data across multiple volumes.

??? info "Can I use network volumes across regions?"

    Typically, network volumes are associated with specific regions, so you can't use them in other regions. Often,
    volumes are also linked to availability zones, but some providers support volumes that can be used across different
    availability zones within the same region.
    
    If you don't want to limit a run to one particular region, you can create different volumes for different regions
    and specify them for the same mount point as [documented above](#attach-network-volume).

??? info "Can I attach network volumes to multiple runs or instances?"
    You can mount a volume in multiple runs. This feature is currently supported only by the `runpod` backend.

## Instance volumes

Instance volumes allow mapping any directory on the instance where the run is executed to any path inside the container.
This means that the data in instance volumes is persisted only if the run is executed on the same instance.

### Attach a volume

A run can configure any number of instance volumes. To attach an instance volume,
specify the `instance_path` and `path` in the `volumes` property:

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

Since persistence isn't guaranteed (instances may be interrupted or runs may occur on different instances), use instance
volumes only for caching or with directories manually mounted to network storage.

!!! info "Backends"
    Instance volumes are currently supported for all backends except `runpod`, `vastai` and `kubernetes`, and can also be used with [SSH fleets](fleets.md#ssh).

??? info "Optional volumes"
    If the volume is not critical for your workload, you can mark it as `optional`.

    <div editor-title=".dstack.yml">

    ```yaml
    type: task

    volumes:
      - instance_path: /dstack-cache
        path: /root/.cache/
        optional: true
    ```

    Configurations with optional volumes can run in any backend, but the volume is only mounted
    if the selected backend supports it.

    </div>

### Use instance volumes for caching

For example, if a run regularly installs packages with `pip install`,
you can mount the `/root/.cache/pip` folder inside the container to a folder on the instance for 
reuse.

<div editor-title=".dstack.yml">

```yaml
type: task

volumes:
  - /dstack-cache/pip:/root/.cache/pip
```

</div>

### Use instance volumes with SSH fleets
    
If you control the instances (e.g. they are on-prem servers configured via [SSH fleets](fleets.md#ssh)), 
you can mount network storage (e.g., NFS or SMB) and use the mount points as instance volumes.

For example, if you mount a network storage to `/mnt/nfs-storage` on all hosts of your SSH fleet,
you can map this directory via instance volumes and be sure the data is persisted.

<div editor-title=".dstack.yml">

```yaml
type: task

volumes:
  - /mnt/nfs-storage:/storage
```

</div>
