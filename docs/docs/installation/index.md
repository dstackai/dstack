# Installation

Follow this guide to install the open-source version of `dstack` server.

## Set up the server

=== "pip"

    <div class="termy">
    
    ```shell
    $ pip install "dstack[all]" -U
    $ dstack server

    Applying ~/.dstack/server/config.yml...

    The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
    The server is running at http://127.0.0.1:3000/
    ```
    
    </div>

=== "Docker"

    <div class="termy">
    
    ```shell
    $ docker run -p 3000:3000 -v $HOME/.dstack/server/:/root/.dstack/server dstackai/dstack

    Applying ~/.dstack/server/config.yml...

    The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
    The server is running at http://127.0.0.1:3000/.
    ```
        
    </div>

!!! info "NOTE:"
    For flexibility, `dstack` server allows you to configure multiple project. The default project is `main`.

### Configure backends

To let `dstack` run workloads in your cloud account(s), you need to configure cloud credentials 
in `~/.dstack/server/config.yml` under the `backends` property of the respective project.

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

!!! info "Default credentials"
    If you have default AWS, GCP, or Azure credentials on your machine, the `dstack` server will pick them up automatically.
    Otherwise, you have to configure them manually.

#### AWS

There are two ways to configure AWS: using an access key or using the default credentials.

=== "Access key"

    Create an access key by following the [this guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-authentication-user.html#cli-authentication-user-get).
    Once you've downloaded the `.csv` file with your IAM user's Access key ID and Secret access key, proceed to 
    configure the backend.
    
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

=== "Default credentials"

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

??? info "Required AWS permissions"
    The following AWS policy permissions are sufficient for `dstack` to work:

    ```
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:*"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "servicequotas:*"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "iam:GetRole",
                    "iam:CreateRole",
                    "iam:AttachRolePolicy",
                    "iam:TagRole"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "iam:CreatePolicy",
                    "iam:TagPolicy"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "iam:GetInstanceProfile",
                    "iam:CreateInstanceProfile",
                    "iam:AddRoleToInstanceProfile",
                    "iam:TagInstanceProfile",
                    "iam:PassRole"
                ],
                "Resource": "*"
            }
        ]
    }
    ```

#### Azure

There are two ways to configure Azure: using a client secret or using the default credentials.

=== "Client secret"

    A client secret can be created using the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli):

    ```shell
    SUBSCRIPTION_ID=...
    az ad sp create-for-rbac 
        --name dstack-app \
        --role Owner \ 
        --scopes /subscriptions/$SUBSCRIPTION_ID \ 
        --query "{ tenant_id: tenant, client_id: appId, client_secret: password }"
    ```

    Once you have `tenant_id`, `client_id`, and `client_secret`, go ahead and configure the backend.

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

=== "Default credentials"

    Obtain the `subscription_id` and `tenant_id` via the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli):
    
    ```shell
    az account show --query "{subscription_id: id, tenant_id: tenantId}"
    ```
     
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

!!! info "NOTE:"
    If you don't know your `subscription_id`, run

    ```shell
    az account show --query "{subscription_id: id}"
    ```

??? info "Required Azure permissions"
    You must have the `Owner` permission for the Azure subscription.
    Please, [let us know](https://discord.gg/u8SmfwPpMd) if your use case requires more granular Azure permissions.

#### GCP

??? info "Enable APIs"
    First, ensure the required APIs are enabled in your GCP `project_id`.

    ```shell
    PROJECT_ID=...
    gcloud config set project $PROJECT_ID
    gcloud services enable cloudapis.googleapis.com
    gcloud services enable compute.googleapis.com 
    ```

There are two ways to configure GCP: using a service account or using the default credentials.

=== "Service account"

    To create a service account, follow [this guide](https://cloud.google.com/iam/docs/service-accounts-create).
    Make sure to grant it the `Service Account User` and `Compute Admin` roles.
    
    After setting up the service account [create a key](https://cloud.google.com/iam/docs/keys-create-delete) for it 
    and download the corresponding JSON file.
    
    Then go ahead and configure the backend by specifying the downloaded file path.
    
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

=== "Default credentials"

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

!!! info "NOTE:"
    If you don't know your GCP project ID, run 

    ```shell
    gcloud projects list --format="json(projectId)"
    ```

??? info "Required GCP permissions"
    The `Service Account User` and `Compute Admin` roles are sufficient for `dstack` to work.

#### Lambda

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

#### TensorDock

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

#### Vast AI

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
    Also, the `vastai` backend supports on-demand instances only. Spot instance support coming soon.

#### DataCrunch

Log into your [DataCrunch](https://cloud.datacrunch.io/signin) account, click Account Settings in the sidebar, find `REST API Credentials` area and then click the `Generate Credentials` button.

Then, go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: datacrunch
    creds:
      type: api_key
      client_id: xfaHBqYEsArqhKWX-e52x3HH7w8T
      client_secret: B5ZU5Qx9Nt8oGMlmMhNI3iglK8bjMhagTbylZy4WzncZe39995f7Vxh8
```

</div>

#### Kubernetes

`dstack` supports both self-managed, and managed Kubernetes clusters.

??? info "Prerequisite"
    To use GPUs with Kubernetes, the cluster must be installed with the 
    [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/index.html).
    
    [//]: # (TODO: Provide short yet clear instructions. Elaborate on whether it works with Kind.)

To configure a Kubernetes backend, specify the path to the kubeconfig file, 
and the port that `dstack` can use for proxying SSH traffic.
In case of a self-managed cluster, also specify the IP address of any node in the cluster.

[//]: # (TODO: Mention that the Kind context has to be selected via `current-context` )

=== "Self-managed"

    Here's how to configure the backend to use a self-managed cluster.

    <div editor-title="~/.dstack/server/config.yml">

    ```yaml
    projects:
    - name: main
      backends:
      - type: kubernetes
        kubeconfig:
          filename: ~/.kube/config
        networking:
          ssh_host: localhost # The external IP address of any node
          ssh_port: 32000 # Any port accessible outside of the cluster
    ```

    </div>

    The port specified to `ssh_port` must be accessible outside of the cluster.
    
    For example, if you are using Kind, make sure to add it via `extraPortMappings`:

    <div editor-title="installation/kind-config.yml"> 

    ```yaml
    kind: Cluster
    apiVersion: kind.x-k8s.io/v1alpha4
    nodes:
    - role: control-plane
      extraPortMappings:
      - containerPort: 32000 # Must be same as `ssh_port`
        hostPort: 32000 # Must be same as `ssh_port`
    ```

    </div>

[//]: # (TODO: Elaborate on the Kind's IP address on Linux)

=== "Managed"
    Here's how to configure the backend to use a managed cluster (AWS, GCP, Azure).

    <div editor-title="~/.dstack/server/config.yml">

    ```yaml
    projects:
    - name: main
      backends:
      - type: kubernetes
        kubeconfig:
          filename: ~/.kube/config
        networking:
          ssh_port: 32000 # Any port accessible outside of the cluster
    ```

    </div>

    The port specified to `ssh_port` must be accessible outside of the cluster.
    
    For example, if you are using EKS, make sure to add it via an ingress rule
    of the corresponding security group:

    ```shell
    aws ec2 authorize-security-group-ingress --group-id <cluster-security-group-id> --protocol tcp --port 32000 --cidr 0.0.0.0/0
    ```

[//]: # (TODO: Ellaborate on gateways, and what backends allow configuring them)

[//]: # (TODO: Should we automatically detect ~/.kube/config)

### Configure regions

In addition to credentials, each backend (except TensorDock, Vast AI, DataCrunch, and Kubernetes) 
optionally allows for region configuration.

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

After you update `~/.dstack/server/config.yml`, make sure to restart the server.

## Set up the CLI

The client is configured via `~/.dstack/config.yml` with the server address, user token, and
the project name. 

If you run `dstack server` on the same machine, it automatically
updates the client configuration for the default project (`main`).

To configure the client on a different machine or for other projects, use [`dstack config`](../reference/cli/index.md#dstack-config).

<div class="termy">

```shell
$ dstack config --url &lt;your server adddress&gt; --project &lt;your project name&gt; --token &lt;your user token&gt;
    
Configurated is updated at ~/.dstack/config.yml
```

</div>
