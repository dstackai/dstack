# Volumes

Volumes allow you to persist data between runs. `dstack` simplifies managing volumes and lets you mount them to a specific
directory when working with dev environments, tasks, and services.

!!! info "Experimental"
    Volumes are currently experimental and only work with the `aws` and `runpod` backends.
    Support for other backends is coming soon.

## Configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `vol.dstack.yml`
are both acceptable).

<div editor-title="vol.dstack.yml"> 

```yaml
type: volume
name: my-new-volume
backend: aws
region: eu-central-1
size: 100GB
```

</div>

If you use this configuration, `dstack` will create a new volume based on the specified options.

!!! info "Registering existing volumes"
    If you prefer not to create a new volume but to reuse an existing one (e.g., created manually), you can 
    [specify its ID via `volume_id`](../reference/dstack.yml/volume.md#register-volume). In this case, `dstack` will register the specified volume so that you can use it with dev environments, tasks, and services.

!!! info "Reference"
    See the [.dstack.yml reference](../reference/dstack.yml/dev-environment.md)
    for all supported configuration options and multiple examples.

## Creating and registering volumes

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

## Attaching volumes

Dev environments, tasks, and services let you attach any number of volumes.
To attach a volume, simply specify its name using the `volumes` property and specify where to mount its contents:

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
ide: vscode
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

## Managing gateways

**Deleting gateways**

When the volume isn't attached to any active dev environment, task, or service, you can delete it using `dstack delete`:

```shell
$ dstack delete -f vol.dstack.yaml
```

If the volume was created using `dstack`, it will be physically destroyed along with the data.
If you've registered an existing volume, it will be de-registered with `dstack` but will keep the data.

**Listing volumes**

The [`dstack volume list`](../reference/cli/index.md#dstack-gateway-list) command lists created and registered volumes.

## FAQ

??? info "Using volumes across backends"
    Since volumes are backed up by cloud network disks, you can only use them within the same cloud. If you need to access
    data across different backends, you should either use object storage or replicate the data across multiple volumes.

??? info "Using volumes across regions"
    Typically, network volumes are associated with specific regions, so you can't use them in other regions. Often,
    volumes are also linked to availability zones, but some providers support volumes that can be used across different
    availability zones within the same region.

??? info "Attaching volumes to multiple runs and instances"
    You can mount a volume in multiple runs.
    This feature is currently supported only by the `runpod` backend.
