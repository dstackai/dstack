# GCP

## 1. Create a project

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

## 2. Create a storage bucket

Once the project is set up, you can proceed and create a storage bucket. This bucket
will be used to store workflow artifacts and metadata.

!!! info "NOTE:"
    Make sure to create the bucket in the location where you'd like to run your workflows.

## 3. Create a service account

The next step is to create a service account in the created project and configure the
following roles for it: `Service Account User`, `Compute Admin`, `Storage Admin`, `Secret Manager Admin`,
and `Logging Admin`.

## 4. Create a service account key

Once the service account is set up, create a key for it and download the corresponding JSON file
to your local machine (e.g. to `~/Downloads/my-awesome-project-d7735ca1dd53.json`).

## 5. Configure the CLI

Once the service account key JSON file is on your machine, you can configure the CLI using the `dstack config` command.

The command will ask you for a path to a service account key file, GCP region and zone, and storage bucket name.

<div class="termy">

```shell
$ dstack config

? Choose backend: gcp
? Enter path to credentials file: ~/Downloads/dstack-d7735ca1dd53.json
? Choose GCP geographic area: North America
? Choose GCP region: us-west1
? Choose GCP zone: us-west1-b
? Choose storage bucket: dstack-dstack-us-west1
? Choose VPC subnet: no preference
```

</div>

That's it! You've configured GCP as a remote.