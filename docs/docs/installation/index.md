# Installation

To install `dstack`, use `pip`:

<div class="termy">
    
    ```shell
    $ pip install "dstack[all]" -U
    ```

</div>

To use the open-source version of `dstack`, you have to configure 
your cloud accounts via `~/.dstack/server/config.yml` and start the `dstack` server.

## Configure backends

To configure cloud accounts, create the    
`~/.dstack/server/config.yml` file, and configure each cloud under the `backends` property.

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

Refer below for examples on how to configure a specific cloud provider.

??? info "Projects"
    For flexibility, `dstack` server permits you to configure backends for multiple projects. 
    If you intend to use only one project, name it `main`.

[//]: # (!!! info "Default credentials")
[//]: # (    If you have default AWS, GCP, or Azure credentials on your machine, the `dstack` server will pick them up automatically.)
[//]: # (    Otherwise, you have to configure them manually.)

### AWS

There are two ways to configure AWS: using an access key or using the default credentials.

=== "Access key"

    Create an access key by following the [this guide :material-arrow-top-right-thin:{ .external }](https://docs.aws.amazon.com/cli/latest/userguide/cli-authentication-user.html#cli-authentication-user-get).
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

??? info "VPC"
    By default, `dstack` uses the default VPC. It's possible to customize it:

    === "vpc_name"

        ```yaml
        projects:
        - name: main
          backends:
            - type: aws
              creds:
                type: default

              vpc_name: my-vpc
        ```

    === "vpc_ids"
        ```yaml
        projects:
        - name: main
          backends:
            - type: aws
              creds:
                type: default

              vpc_ids:
                us-east-1: vpc-0a2b3c4d5e6f7g8h
                us-east-2: vpc-9i8h7g6f5e4d3c2b
                us-west-1: vpc-4d3c2b1a0f9e8d7
        ```

    Note, the VPCs are required to have a public subnet.

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

### Azure

There are two ways to configure Azure: using a client secret or using the default credentials.

=== "Client secret"

    A client secret can be created using the [Azure CLI :material-arrow-top-right-thin:{ .external }](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli):

    ```shell
    SUBSCRIPTION_ID=...
    az ad sp create-for-rbac 
        --name dstack-app \
        --role $DSTACK_ROLE \ 
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

    Obtain the `subscription_id` and `tenant_id` via the [Azure CLI :material-arrow-top-right-thin:{ .external }](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli):
    
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
    The following Azure permissions are sufficient for `dstack` to work:
    ```
    {
        "properties": {
            "roleName": "dstack-role",
            "description": "Minimal reqired permissions for using Azure with dstack",
            "assignableScopes": [
                "/subscriptions/${YOUR_SUBSCRIPTION_ID}"
            ],
            "permissions": [
                {
                  "actions": [
                      "Microsoft.Authorization/*/read",
                      "Microsoft.Compute/availabilitySets/*",
                      "Microsoft.Compute/locations/*",
                      "Microsoft.Compute/virtualMachines/*",
                      "Microsoft.Compute/virtualMachineScaleSets/*",
                      "Microsoft.Compute/cloudServices/*",
                      "Microsoft.Compute/disks/write",
                      "Microsoft.Compute/disks/read",
                      "Microsoft.Compute/disks/delete",
                      "Microsoft.Network/networkSecurityGroups/*",
                      "Microsoft.Network/locations/*",
                      "Microsoft.Network/virtualNetworks/*",
                      "Microsoft.Network/networkInterfaces/*",
                      "Microsoft.Network/publicIPAddresses/*",
                      "Microsoft.Resources/subscriptions/resourceGroups/read",
                      "Microsoft.Resources/subscriptions/resourceGroups/write",
                      "Microsoft.Resources/subscriptions/read"
                  ],
                  "notActions": [],
                  "dataActions": [],
                  "notDataActions": []
                }
            ]
        }
    }
    ```

### GCP

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

    To create a service account, follow [this guide :material-arrow-top-right-thin:{ .external }](https://cloud.google.com/iam/docs/service-accounts-create).
    Make sure to grant it the `Service Account User` and `Compute Admin` roles.
    
    After setting up the service account [create a key :material-arrow-top-right-thin:{ .external }](https://cloud.google.com/iam/docs/keys-create-delete) for it
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
    The following GCP permissions are sufficient for `dstack` to work:

    ```
    compute.disks.create
    compute.firewalls.create
    compute.images.useReadOnly
    compute.instances.create
    compute.instances.delete
    compute.instances.get
    compute.instances.setLabels
    compute.instances.setMetadata
    compute.instances.setTags
    compute.networks.updatePolicy
    compute.regions.list
    compute.subnetworks.use
    compute.subnetworks.useExternalIp
    compute.zoneOperations.get
    ```

### Lambda

Log into your [Lambda Cloud :material-arrow-top-right-thin:{ .external }](https://lambdalabs.com/service/gpu-cloud) account, click API keys in the sidebar, and then click the `Generate API key`
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

Log into your [TensorDock :material-arrow-top-right-thin:{ .external }](https://marketplace.tensordock.com/) account, click API in the sidebar, and use the `Create an Authorization`
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

### Vast.ai

Log into your [Vast.ai :material-arrow-top-right-thin:{ .external }](https://cloud.vast.ai/) account, click Account in the sidebar, and copy your
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

### CUDO

Log into your [CUDO Compute :material-arrow-top-right-thin:{ .external }](https://compute.cudo.org/) account, click API keys in the sidebar, and click the `Create an API key` button.

Ensure you've created a project with CUDO Compute, then proceed to configuring the backend.

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: cudo
    project_id: my-cudo-project
    creds:
      type: api_key
      api_key: 7487240a466624b48de22865589
```

</div>

### RunPod

Log into your [RunPod :material-arrow-top-right-thin:{ .external }](https://www.runpod.io/console/) console, click Settings in the sidebar, expand the `API Keys` section, and click
the button to create a key.

Then proceed to configuring the backend.

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: runpod
    creds:
      type: api_key
      api_key: US9XTPDIV8AR42MMINY8TCKRB8S4E7LNRQ6CAUQ9
```

</div>

!!! warning "NOTE:"
    If you're using a custom Docker image, its entrypoint cannot be anything other than `/bin/bash` or `/bin/sh`. 
    See the [issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1137) for more details.

!!! info "NOTE:"
    The `runpod` backend supports on-demand instances only. Spot instance support coming soon.

### DataCrunch

Log into your [DataCrunch :material-arrow-top-right-thin:{ .external }](https://cloud.datacrunch.io/signin) account, click Account Settings in the sidebar, find `REST API Credentials` area and then click the `Generate Credentials` button.

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

### Kubernetes

`dstack` supports both self-managed, and managed Kubernetes clusters.

??? info "Prerequisite"
    To use GPUs with Kubernetes, the cluster must be installed with the 
    [NVIDIA GPU Operator :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/index.html).
    
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

[//]: # (TODO: Elaborate on gateways, and what backends allow configuring them)

[//]: # (TODO: Should we automatically detect ~/.kube/config)

## Start the server

Once the `~/.dstack/server/config.yml` file is configured, proceed to start the server:

=== "pip"

    <div class="termy">
    
    ```shell
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
    The server is running at http://127.0.0.1:3000/
    ```
        
    </div>

[//]: # (After you update `~/.dstack/server/config.yml`, make sure to restart the server.)

## Configure the CLI

To point the CLI to the `dstack` server, you need to configure `~/.dstack/config.yml` 
with the server address, user token and project name.

<div class="termy">

```shell
$ dstack config --url http://127.0.0.1:3000 \
    --project main \
    --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
    
Configuration is updated at ~/.dstack/config.yml
```

</div>

[//]: # (The `dstack server` command automatically updates `~/.dstack/config.yml`)
[//]: # (with the `main` project.)

## What's next?

1. Follow [quickstart](../quickstart.md)
2. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/README.md)
3. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)