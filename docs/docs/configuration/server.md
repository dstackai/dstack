# Server configuration

If you're using the open-source server, you can configure your own 
cloud accounts, allowing `dstack` to provision workloads there.

For flexibility, the server allows you to have multiple projects and users.

To configure a cloud account, specify its settings in `~/.dstack/server/config.yml` under the `backends` property 
of the respective project.

Example:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: aws
    creds:
      type: access_key
      access_key: AIZKISCVKUKO5AAKLAEH
      secret_key: QSbmpqJIUBn1V5U3pyM9S6lwwiu8/fOJ2dgfwFdW
```

</div>

!!! info "Default project"
    The default project is `main`. The CLI and API are automatically configured to use it (through `~/.dstack/config.yml`).

[//]: # (If you run the `dstack` server without creating `~/.dstack/server/config.yml`, `dstack` will attempt to automatically detect the)
[//]: # (default credentials for AWS, GCP, and Azure and create the configuration.)

## Cloud credentials

### AWS

[//]: # (TODO: Permissions)

There are two ways to configure AWS: using an access key or using the default credentials.

#### Access key

To create an access key, follow [this guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-authentication-user.html#cli-authentication-user-get). 

Once you've downloaded the `.csv` file containing your IAM user's `Access key ID` and `Secret access key`,
go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: aws
    creds:
      type: access_key
      access_key: KKAAUKLIZ5EHKICAOASV
      secret_key: pn158lMqSBJiySwpQ9ubwmI6VUU3/W2fdJdFwfgO
```

</div>

#### Default credentials

If you have default credentials set up (e.g. in `~/.aws/credentials`), configure the backend like this:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: aws
    creds:
      type: default
```

</div>

### Azure

!!! info "Permission"
    You must have the `Owner` permission for the Azure subscription.

There are two ways to configure Azure: using a client secret or using the default credentials.

#### Client secret

A client secret can be created using the Azure CLI: (1)
{ .annotate } 

1.  If you don't know your `subscription_id`, run 
    ```shell
    az account show --query "{subscription_id: id}"
    ```  

<div class="termy">

```shell
$ SUBSCRIPTION_ID=...
$ az ad sp create-for-rbac --name dstack-app --role Owner --scopes /subscriptions/$SUBSCRIPTION_ID --query "{ tenant_id: tenant, client_id: appId, client_secret: password }"
```

</div>

Once you have `tenant_id`, `client_id`, and `client_secret`, go ahead and configure the backend.

Example:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: azure
    subscription_id: 06c82ce3-28ff-4285-a146-c5e981a9d808
    tenant_id: f84a7584-88e4-4fd2-8e97-623f0a715ee1
    creds:
      type: client
      client_id: acf3f73a-597b-46b6-98d9-748d75018ed0
      client_secret: 1Kb8Q~o3Q2hdEvrul9yaj5DJDFkuL3RG7lger2VQ
```

</div>

#### Default credentials

Another way to configure Azure is through default credentials.

Obtain the `subscription_id` and `tenant_id` via the Azure CLI:

<div class="termy">

```shell
$ az account show --query "{subscription_id: id, tenant_id: tenantId}"
```

</div>

Then proceed to configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: azure
    subscription_id: 06c82ce3-28ff-4285-a146-c5e981a9d808
    tenant_id: f84a7584-88e4-4fd2-8e97-623f0a715ee1
    creds:
      type: default
```

</div>

### GCP

??? info "Enable APIs"
    First, ensure the required APIs are enabled in your GCP `project_id`. (1)
    { .annotate } 

    1.  If you don't know your GCP `project_id`, run 
        ```shell
        gcloud projects list --format="json(projectId)"
        ```  

    ```
    PROJECT_ID=...
    gcloud config set project $PROJECT_ID
    gcloud services enable cloudapis.googleapis.com
    gcloud services enable compute.googleapis.com 
    ```

There are two ways to configure GCP: using a service account or using the default credentials.

#### Service account

To create a service account, follow [this guide](https://cloud.google.com/iam/docs/service-accounts-create).
Make sure to grant it the `Service Account User`, and `Compute Admin` roles.

After setting up the service account [create a key](https://cloud.google.com/iam/docs/keys-create-delete) for it 
and download the corresponding JSON file.

Then go ahead and configure the backend by specifying the downloaded file path. (1) 
{ .annotate }

1.  If you don't know your GCP `project_id`, run 
    ```shell
    gcloud projects list --format="json(projectId)"
    ```

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: gcp
    project_id: gcp-project-id
    creds:
      type: service_account
      filename: ~/.dstack/server/gcp-024ed630eab5.json
```

</div>

#### Default credentials

Example: (1) 
{ .annotate }

1.  If you don't know your GCP `project_id`, run 
    ```shell
    gcloud projects list --format="json(projectId)"
    ```

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: gcp
    project_id: gcp-project-id
    creds:
      type: default
```

</div>

### Lambda

Log into your [Lambda Cloud](https://lambdalabs.com/service/gpu-cloud) account, click API keys in the sidebar, and then click the `Generate API key`
button to create a new API key.

Then, go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: lambda
    creds:
      type: api_key
      api_key: eersct_yrpiey-naaeedst-tk-_cb6ba38e1128464aea9bcc619e4ba2a5.iijPMi07obgt6TZ87v5qAEj61RVxhd0p
```

</div>

### TensorDock

Log into your [TensorDock](https://marketplace.tensordock.com/) account, click API in the sidebar, and use the `Create an Authorization`
section to create a new authorization key.

Then, go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: tensordock
    creds:
      type: api_key
      api_key: 248e621d-9317-7494-dc1557fa5825b-98b
      api_token: FyBI3YbnFEYXdth2xqYRnQI7hiusssBC
```

</div>

!!! info "NOTE:"
    The `tensordock` backend supports on-demand instances only. Spot instance support coming soon.

### Vast AI

Log into your [Vast AI](https://cloud.vast.ai/) account, click Account in the sidebar, and copy your
API Key.

Then, go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: vastai
    creds:
      type: api_key
      api_key: d75789f22f1908e0527c78a283b523dd73051c8c7d05456516fc91e9d4efd8c5
```

</div>

!!! info "NOTE:"
    The `vastai` backend supports on-demand instances only. Spot instance support coming soon.

## Cloud regions

In addition to credentials, each cloud (except TensorDock) optionally allows for region configuration.

Example:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: aws
    regions: [us-west-2, eu-west-1]
    creds:
      type: access_key
      access_key: AIZKISCVKUKO5AAKLAEH
      secret_key: QSbmpqJIUBn1V5U3pyM9S6lwwiu8/fOJ2dgfwFdW
```

</div>

If regions aren't specified, `dstack` will use all available regions.
