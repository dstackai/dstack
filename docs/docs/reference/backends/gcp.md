# GCP

The GCP backend type allows to provision infrastructure and store state and artifacts in a GCP account.

Follow the step-by-step guide below to configure a project with this backend.

## 1. Enable APIs

First, ensure that the required APIs are [enabled](https://cloud.google.com/endpoints/docs/openapi/enable-api) in your GCP project.

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

Once the APIs are enabled, proceed and create a storage bucket. `dstack` will use this bucket to store state and
artifacts.

!!! info "NOTE:"
    Make sure that the bucket is created in the same region where you plan to provision
    infrastructure.

## 3. Create a service account

The next step is to [create a service account](https://cloud.google.com/iam/docs/service-accounts-create) and configure the
following roles for it: `Service Account User`, `Compute Admin`, `Storage Admin`, `Secret Manager Admin`,
and `Logging Admin`.

## 4. Create a service account key

Once the service account is set up, [create a key](https://cloud.google.com/iam/docs/keys-create-delete) for it and
download the corresponding JSON file.

## 5. Create a project

Now that you have a service account key, log in to the Hub, open the `Projects` page, click `Add`, and select `GCP` in
the `Type` field.

![](../../../assets/images/dstack-hub-create-gcp-project.png){ width=800 }

### Fields reference

The following fields are required:

- `Service account` - (Required) The JSON file of the [Service account key](#4-create-a-service-account-key) to authenticate `dstack` 
- `Location` - (Required) The location where `dstack` will create provision infrastructure and store state and artifacts
- `Region` - (Required) The region where `dstack` will create provision infrastructure and store state and artifacts
- `Zone` - (Required) The zone where `dstack` will create provision infrastructure and store state and artifacts
- `Bucket` - (Required) The [Storage bucket](#2-create-a-storage-bucket) to store state and artifacts (must be in the same region)

The following arguments are optional:

- `Subnet` - (Optional) The EC2 subnet is required to provision infrastructure using a non-default VPC and subnet. If
  not specified, dstack will use the default VPC and subnet.

## 6. Configure the CLI

!!! info "NOTE:"
    Once you have created the project, feel free to use the CLI code snippet to configure it for use with the created project.

    [Learn more →](../../../guides/projects#configuring-the-cli){ .md-button .md-button--primary }