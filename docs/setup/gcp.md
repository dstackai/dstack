# GCP

`dstack` enables the running remote workflows on AWS. It automatically provisions cloud resources and
destroys them upon workflow completion. Check out the following instructions to configure `dstack` for use with AWS.

## Create a project

In order to use GCP as a remote, you first have to create a project in your GCP account
and make sure that the required APIs and enabled for it.

??? info "Required APIs"
    Here's the list of APIs that have to be enabled for the project.

    ```
    cloudapis.googleapis.com
    compute.googleapis.com 
    logging.googleapis.com
    secretmanager.googleapis.com
    storage-api.googleapis.com
    storage-component.googleapis.com 
    storage.googleapis.com 
    ```

## Create a storage bucket

Once the project is set up, you can proceed and create a storage bucket. This bucket
will be used to store workflow artifacts and metadata.

!!! info "NOTE:"
    Make sure to create the bucket in the location where you'd like to run your workflows.

## Create a service account

The next step is to create a service account in the created project and configure the
following roles for it: `Service Account User`, `Compute Admin`, `Storage Admin`, `Secret Manager Admin`,
and `Logging Admin`.

## Create a service account key

Once the service account is set up, create a key for it and download the corresponding JSON file
to your local machine (e.g. to `~/Downloads/my-awesome-project-d7735ca1dd53.json`).

## Configure the CLI

In order to configure the CLI, so it runs remote workflows in your GCP account, you have to use 
the `dstack config` command.

<div class="termy">

```shell
$ dstack config
? Choose backend. Use arrows to move, type to filter
  [aws]
> [gcp]
  [hub]
```

</div>

If you want the CLI to run remote workflows directly in cloud using your local credentials, choose `gcp`.
It will prompt you to select a location (where to run workflows), a storage bucket, etc.

If you prefer managing cloud credentials and settings through a user interface (e.g. while working in a team),
select `hub`. Check [Hub](hub.md) for more details.