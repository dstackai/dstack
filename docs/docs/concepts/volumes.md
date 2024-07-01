# Volumes

Volumes allow persisting data between runs. When you add a volume,
`dstack` provisions a network disk in the cloud, such as an AWS EBS.
Then you can mount the volume as a directory in a run and store data there.
After the run is terminated, the volume can be mounted again and the stored data will persist.

`dstack` supports creating new volumes (a.k.a. `dstack`-managed volumes)
and also registering existing volumes (a.k.a. external volumes).
The latter allows accessing data that is already stored on some volume, such as pre-processed training data.

!!! info "Backends"
    Currently, volumes are supported only for `aws`. Support for other backends is coming soon!

!!! info "File system"
    `dstack` creates an ext4 file system on `dstack`-managed volumes automatically.
    If you register an external volume, you must ensure it already has a file system.

## Creating new volumes

First create a `volume` configuration file and specify `size` of the volume you'd like to provision:

<div editor-title="new-volume.dstack.yml"> 

```yaml
type: volume
name: my-new-volume
backend: aws
region: eu-central-1
size: 100GB
```

</div>

Then apply the configuration to create the volume:

<div class="termy">

```shell
$ dstack apply -f new-volume.dstack.yml
Volume my-new-volume does not exist yet. Create the volume? [y/n]: y
 NAME           BACKEND  REGION        STATUS     CREATED 
 my-new-volume  aws      eu-central-1  submitted  now     

```

</div>

The volume is created and can be mounted in runs!

!!! info "Volume parameters"
    `dstack` has default volume parameters for every backend so you can specify only `size`.
    On AWS, `dstack` provisions EBS gp3 volumes.


## Register existing volumes

If you already have a volume in your cloud account that you'd like to use with `dstack`,
create a `volume` configuration file with `volume_id` specified:

<div editor-title="external-volume.dstack.yml"> 

```yaml
type: volume
name: my-external-volume
backend: aws
region: eu-central-1
volume_id: vol1235
```

</div>

Then apply the configuration to register the volume:

<div class="termy">

```shell
$ dstack apply -f external-volume.dstack.yml
Volume my-external-volume does not exist yet. Create the volume? [y/n]: y
 NAME                BACKEND  REGION        STATUS     CREATED 
 my-external-volume  aws      eu-central-1  submitted  now     

```

</div>

The volume is registered and can be mounted in runs!


## Mount volumes in runs

Suppose we need to run a dev environment.
We could mount a volume and store our work there so it's not lost between run restarts or instance interruptions.
We do it by specifying a list of `volumes`.
Each item in `volumes` should have `name` of the volume and `path` where the volume should be mounted in the run.
Here's what it looks like:

<div editor-title="dev.dstack.yml"> 

```yaml
type: dev-environment
ide: vscode
volumes:
  - name: my-new-volume
    path: /volume_data
```

</div>

Then we can run this `dev-environment` configuration, ssh into the run, and see `/volume_data`:

```shell
-(workflow) root@ip-10-0-10-73:/workflow# ls -l /
total 92
drwxr-xr-x   2 root root  4096 Apr 15  2020 home
...
drwxr-xr-x   3 root root  4096 Jun 28 07:02 volume_data
drwxr-xr-x   5 root root  4096 Jun 28 07:13 workflow
```

## Deleting volumes

After the run is stopped, a volume can be deleted with `dstack delete`:

```shell
$ dstack delete -f .dstack/confs/volume.yaml
Delete the volume my-new-volume? [y/n]: y
Volume my-new-volume deleted
```

Note that deleting `dstack`-managed volumes destroys all the volumes data!
Deleting external volumes makes `dstack` "forget" about the volumes, but they remain in the cloud.

## FAQ

1. Can I mount volumes from one cloud on instances from other clouds?

    No. Since volumes are backed up by cloud network disks, they can only be used with instances in the same cloud.
    If you need to access data from different clouds, consider uploading it to an object storage.

2. Can I mount volumes from one region/zone on instances from other regions/zones?

    It depends on the cloud and volume type. Generally, network volumes are tied to regions so they cannot be
    used in other regions. Volumes are also often tied to availability zones but
    some clouds support volumes that can be used across availability zones within a region.
