# Clouds

For every project, `dstack` allows you to configure multiple cloud accounts. 

To configure your cloud account, provide their credentials and other settings via `~/.dstack/server/config.yml`.

Example:

<div editor-title=".dstack/server/config.yml">

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

Each cloud account should be listed separately under the `backends` property for the respective project.

!!! info "Default project"
    The default project is `main`. The CLI and API are automatically configured to use it (through `~/.dstack/config.yml`).

[//]: # (If you run dstack server without creating `~/.dstack/server/config.yml`, `dstack` will attempt to automatically detect the)
[//]: # (default credentials for AWS, GCP, and Azure and create the configuration.)

## AWS

[//]: # (TODO: Permissions)

There are two ways to configure AWS: using an access key or using the default credentials.

### Access key

To create an access key, follow [this guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-authentication-user.html#cli-authentication-user-get). 

Once you've downloaded the `.csv` file containing your IAM user's `Access key ID` and `Secret access key`,
go ahead and configure the backend:

<div editor-title=".dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: aws
    regions: [us-west-2, eu-west-1]
    creds:
      type: access_key
      access_key: KKAAUKLIZ5EHKICAOASV
      secret_key: pn158lMqSBJiySwpQ9ubwmI6VUU3/W2fdJdFwfgO
```

</div>

### Default credentials

If you have default credentials set up (e.g. in `~/.aws/credentials`), configure the backend like this:

<div editor-title=".dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: aws
    regions: [us-west-2, eu-west-1]
    creds:
      type: access_key
```

</div>

## Azure

!!! info "Permission"
    You must have the `Owner` permission for the Azure subscription.

There are two ways to configure Azure: using a client secret or using the default credentials.

### Client secret

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

<div editor-title=".dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: azure
    subscription_id: 06c82ce3-28ff-4285-a146-c5e981a9d808
    tenant_id: f84a7584-88e4-4fd2-8e97-623f0a715ee1
    locations: [eastus, westeurope]
    creds:
      type: client
      client_id: acf3f73a-597b-46b6-98d9-748d75018ed0
      client_secret: 1Kb8Q~o3Q2hdEvrul9yaj5DJDFkuL3RG7lger2VQ
```

</div>

### Default credentials

Another way to configure Azure is through default credentials.

Obtain the `subscription_id` and `tenant_id` via the Azure CLI:

<div class="termy">

```shell
$ az account show --query "{subscription_id: id, tenant_id: tenantId}"
```

</div>

Then proceed to configure the backend:

<div editor-title=".dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: azure
    subscription_id: 06c82ce3-28ff-4285-a146-c5e981a9d808
    tenant_id: f84a7584-88e4-4fd2-8e97-623f0a715ee1
    locations: [eastus, westeurope]
    creds:
      type: default
```

</div>

## GCP

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
    gcloud services enable logging.googleapis.com
    gcloud services enable secretmanager.googleapis.com
    gcloud services enable storage-api.googleapis.com
    gcloud services enable storage-component.googleapis.com 
    gcloud services enable storage.googleapis.com 
    ```

There are two ways to configure GCP: using a service account or using the default credentials.

### Service account

To create a service account, follow [this guide](https://cloud.google.com/iam/docs/service-accounts-create).
Make sure to grant it the `Service Account User`, and `Compute Admin` roles.

After setting up the service account [create a key](https://cloud.google.com/iam/docs/keys-create-delete) for it 
and download the corresponding JSON file.

Then go ahead and configure the backend. Specify both the downloaded file path and its contents. (1) 
{ .annotate }

1.  If you don't know your GCP `project_id`, run 
    ```shell
    gcloud projects list --format="json(projectId)"
    ```

<div editor-title=".dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: gcp
    project_id: gcp-project-id
    regions: [us-east1, europe-west1]
    creds:
      type: service_account
      filename: ~/Downloads/gcp-024ed630eab5.json
      data: |
        {
          "type": "service_account",
          "project_id": "dstack",
          "private_key_id": "097b26661309a4ee8cab014271eb57414a3df2aa",
          "private_key": "-----BEGIN PRIVATE KEY-----\ngGgACEEKiSgg0Q4MA9ZuABBYIIkkZtkQDhA6wAoEgDADAISABSBzvNgwAFqIB/91\jLxrnhncSk2CbgrBRORwAEd3gMQjaMibnUw4YLoFILZd4FCXsgSgnoQvvhbkf/lcE\LjzBB4Jjx9UrRdOQFyw8WGlRnUwXWDplP/eApT/dfkPbS9LhOyyhTCJYdmwUjJ59h\ZpKWf9Ftyi9mb4f3tgij3IdgXfUycZnMq4N/6qiedK2YbbC5f+jjcXw81Vns2/voR\fkqSrd9cernHX4uuI7BU/TEL1Hx1KATpt+UaIFrsCVtRMVfi9yamBueffSWvnpp/a\8m4R4ynkH5c00q75E2G95dAkJ273xH9fLyVEnXxtw7rqwfh3/8DzCPeN+l+y9GVY9\yBXnrAE15aEDCJ1DmAAPwEMY58AjQfggXLgN/ELJsgkG6AFouv7ph6PpAgubAUOVH\ondo/npWW4NEO0p7OC6jneustUtIAizUv3Ly9sIcdW+2v8Jf92w2AMOBXVif93fMF\MvVnGfMKGGqWqr+D0DrOX2ZSeVHffZE1CLYQtPJJ1zXBb5b1Y/WZJ1i0UnD0E9OmI\InaW/EqZSCFiKL5rMVhrUuPA55Uo3IX3Sd21jdt1lW0N1R4nlRT5mbvh4SGXvATH3\ns+qKZTyFW2idi3OeQcUFj+B82zz6NEuf6lvRjeOfyGTymmKQ0l3vEMhBC30EyXHI\fpCTnru2mzTNh2TXZrp124FSxQ8CPFFm1eeby1o+eFKoBJS1Q22Ngg6YQfea4QID/\tLonY+auvs/UYn564fDqJ/4iUt4paI0QpYOJPDbSnhM3gArMSerHgLdtXM5s8pW+B\IhMLb3Fu4nRlzf69kEOHB0GraYshb4+ZK6oT1Yem1oi1QBsjPT6PAgWAQIX23+Ar5\DkG5Gg7O0aJeBqR7x4Wnn2JJzwRQqlTHn32eQW1Z7jbRmSIbVZELFruK+lWOLL5zb\6qILdSr3M3R0E1N6nECQlb9AQ5OVqmArAQHiYFh0XuvxkDPvIzjXKUaGiB7ML6BXb\bB7gwP8krk6bldWbOnAtugrnHAnnaIDed3n3c9/tDtX4zNQyOfAeNU1Zc0Q4e5DMx\JPHHbBYtnI7BslmeGgG6kKnY0w/aHPLL/by9PF+cAB+Tse+63SvGdtUSz3Zadsetl\EZFlz2QbQVzkmYTCLIm9nvb8auTN+nnryzCtcQ3n5tfafIq944kYuJFoHoNObY6QL\TMOIVnChCNZyOMINKevTfpXKU9PT8qQXF8CLW4Yvcu7Q/ABGKx5KAKkVBzUzoY7Rt\nQTH/J84+swh8xw0VLxx2TxuYJjsesc+MU1vEbL2xncJ8gWcmilJUgj0sWrDo9PBc\pPVSO1d8b5PnkzEkf+yfs/8+zh5g3OjxZxY/oF4uI7qwTQI+0WBVCBHAEvjQmlIQe\5PYXkBSOGjjsATm2j2CnjbgO2s/Gi/VBqUFnUvJAAGng2Ao/ZCzyLWZdrTN4PVBtJ\UR1nwQptqfL3O+CIUgNg4Ee8mU75jw1xRg7jhmQ9s/TgL6bD00RaM9y/j8SG5bNr6\sPuQ2dnzbb5HH39TYqhOIRYGiJGXDtl+Eslhlat9WDYm+Fu8s31udYTg3yP9TIOs/\3HsTclgpnouYKZ30rxwwTHQg+\n-----END PRIVATE KEY-----\n",
          "client_email": "024ed630eab5@dstack.iam.gserviceaccount.com",
          "client_id": "181099069112520110809",
          "auth_uri": "https://accounts.google.com/o/oauth2/auth",
          "token_uri": "https://oauth2.googleapis.com/token",
          "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
          "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/024ed630eab5%40024ed630eab5.iam.gserviceaccount.com"
        }
```

</div>

### Default credentials

Example: (1) 
{ .annotate }

1.  If you don't know your GCP `project_id`, run 
    ```shell
    gcloud projects list --format="json(projectId)"
    ```

<div editor-title=".dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: gcp
    project_id: gcp-project-id
    regions: [us-east1, europe-west1]
    creds:
      type: default
```

</div>

## Lambda

Log into your Lambda Cloud account, click API keys in the sidebar, and then click the `Generate API key`
button to create a new API key.

Then, go ahead and configure the backend:

<div editor-title=".dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: lambda
    regions: [us-west-2, eu-west-1]
    creds:
      type: api_key
      api_key: eersct_yrpiey-naaeedst-tk-_cb6ba38e1128464aea9bcc619e4ba2a5.iijPMi07obgt6TZ87v5qAEj61RVxhd0p
```

</div>

[//]: # (TODO: Make regions optional)