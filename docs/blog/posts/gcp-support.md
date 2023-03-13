---
date: 2023-03-13
authors: 
  - peterschmidt85
description: The latest update of dstack now supports Google Cloud Platform (GCP).
---

# GCP support just landed

__The latest update of dstack now supports Google Cloud Platform (GCP).__

With the release of version 0.2 of dstack, it is now possible to configure GCP as a remote. All features that were
previously available for AWS,
except [real-time artifacts](https://docs.dstack.ai/basics/artifacts/#real-time-artifacts), are now available for GCP as
well.

<!-- more -->

This means that you can define your ML workflows in code and easily run them locally or remotely in your GCP account.

`dstack` automatically creates and deletes cloud instances as needed, and assists in setting up the environment, including
pipeline dependencies, and saving/loading artifacts. 

No code changes are required since ML workflows are described in YAML. You won't need to deal with Docker, Kubernetes,
or stateful UI.

_This article will explain how to use `dstack` to run remote ML workflows on GCP._

## Quick start

### Prerequisites

Ensure that you have installed the latest version of `dstack` before proceeding.

```shell hl_lines="1"
pip install dstack --upgrade
```

By default, workflows run locally. To run workflows remotely, e.g. on a GCP account), you must configure a
remote using the `dstack config` command. Follow the steps below to do so.

### 1. Create a project

First you have to create a project in your GCP account, link a billing to it, and make sure that the required APIs and enabled for it.

```
cloudapis.googleapis.com
compute.googleapis.com 
logging.googleapis.com
secretmanager.googleapis.com
storage-api.googleapis.com
storage-component.googleapis.com 
storage.googleapis.com 
```

### 2. Create a storage bucket

Once the project is set up, you can proceed and create a storage bucket. This bucket
will be used to store workflow artifacts and metadata.

!!! info "NOTE:"
    Make sure to create the bucket in the sane location where you'd like to run your workflows.

### 3. Create a service account

The next step is to create a service account in the created project and configure the
following roles for it: `Service Account User`, `Compute Admin`, `Storage Admin`, `Secret Manager Admin`,
and `Logging Admin`.

Once the service account is set up, create a key for it and download the corresponding JSON file
to your local machine (e.g. to `~/Downloads/my-awesome-project-d7735ca1dd53.json`).

### 4. Configure the CLI

Once the service account key JSON file is on your machine, you can configure the CLI:

```shell hl_lines="1"
dstack config
```

The command will ask you for a path to the key, GCP region and zone, and storage bucket name.

![dstack config](../../assets/dstack-config-gcp.png)

That's it! Now you can run remote workflows on GCP.