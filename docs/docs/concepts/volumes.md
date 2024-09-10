# Volumes

Volumes allow you to persist data between runs. `dstack` allows to create and attach volumes to 
dev environments, tasks, and services.

> Volumes are currently supported with the `aws`, `gcp`, and `runpod` backends.
Support for other backends and SSH fleets is coming soon.

## Define a configuration

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

## Create, register, or update a volume

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

## Attach a volume

Dev environments, tasks, and services let you attach any number of volumes.
To attach a volume, simply specify its name using the `volumes` property and specify where to mount its contents:

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
```

</div>

Once you run this configuration, the contents of the volume will be attached to `/volume_data` inside the dev environment, 
and its contents will persist across runs.

!!! info "Limitations"
    When you're running a dev environment, task, or service with `dstack`, it automatically mounts the project folder contents
    to `/workflow` (and sets that as the current working directory). Right now, `dstack` doesn't allow you to 
    attach volumes to `/workflow` or any of its subdirectories.

## Manage volumes

### List volumes

The [`dstack volume list`](../reference/cli/index.md#dstack-gateway-list) command lists created and registered volumes:

```
$ dstack volume list
NAME            BACKEND  REGION        STATUS  CREATED
 my-new-volume  aws      eu-central-1  active  3 weeks ago
```

### Delete volumes

When the volume isn't attached to any active dev environment, task, or service, you can delete it using `dstack delete`:

```shell
$ dstack delete -f vol.dstack.yaml
```

If the volume was created using `dstack`, it will be physically destroyed along with the data.
If you've registered an existing volume, it will be de-registered with `dstack` but will keep the data.

## FAQ

##### Can I use volumes across backends?

Since volumes are backed up by cloud network disks, you can only use them within the same cloud. If you need to access
data across different backends, you should either use object storage or replicate the data across multiple volumes.

##### Can I use volumes across regions?

Typically, network volumes are associated with specific regions, so you can't use them in other regions. Often,
volumes are also linked to availability zones, but some providers support volumes that can be used across different
availability zones within the same region.

##### Can I attach volumes to multiple runs or instances?

You can mount a volume in multiple runs. This feature is currently supported only by the `runpod` backend.