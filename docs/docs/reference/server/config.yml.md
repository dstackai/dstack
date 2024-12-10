# ~/.dstack/server/config.yml

The `~/.dstack/server/config.yml` file is used
to [configure](../../installation/index.md#1-configure-backends) the `dstack` server cloud accounts
and other sever-level settings such as encryption.

## Backends

> The `dstack` server allows you to configure backends for multiple projects.
> If you don't need multiple projects, use only the `main` project.

Each cloud account must be configured under the `backends` property of the respective project.
See the examples below.

### Cloud providers

#### AWS

There are two ways to configure AWS: using an access key or using the default credentials.

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

??? info "Required permissions"
    The following AWS policy permissions are sufficient for `dstack` to work:

    ```
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:AttachVolume",
                    "ec2:AuthorizeSecurityGroupEgress",
                    "ec2:AuthorizeSecurityGroupIngress",
                    "ec2:CreatePlacementGroup",
                    "ec2:CancelSpotInstanceRequests",
                    "ec2:CreateSecurityGroup",
                    "ec2:CreateTags",
                    "ec2:CreateVolume",
                    "ec2:DeletePlacementGroup",
                    "ec2:DeleteVolume",
                    "ec2:DescribeAvailabilityZones",
                    "ec2:DescribeCapacityReservations"
                    "ec2:DescribeImages",
                    "ec2:DescribeInstances",
                    "ec2:DescribeInstanceAttribute",
                    "ec2:DescribeInstanceTypes",
                    "ec2:DescribeRouteTables",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeVpcs",
                    "ec2:DescribeVolumes",
                    "ec2:DetachVolume",
                    "ec2:RunInstances",
                    "ec2:TerminateInstances"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "servicequotas:ListServiceQuotas",
                    "servicequotas:GetServiceQuota"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "elasticloadbalancing:CreateLoadBalancer",
                    "elasticloadbalancing:CreateTargetGroup",
                    "elasticloadbalancing:CreateListener",
                    "elasticloadbalancing:RegisterTargets",
                    "elasticloadbalancing:AddTags",
                    "elasticloadbalancing:DeleteLoadBalancer",
                    "elasticloadbalancing:DeleteTargetGroup",
                    "elasticloadbalancing:DeleteListener",
                    "elasticloadbalancing:DeregisterTargets"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "acm:DescribeCertificate",
                    "acm:ListCertificates"
                ],
                "Resource": "*"
            }
        ]
    }
    ```

    The `elasticloadbalancing:*` and `acm:*` permissions are only needed for provisioning gateways with ACM (AWS Certificate Manager) certificates.

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

                default_vpcs: true
                vpc_ids:
                  us-east-1: vpc-0a2b3c4d5e6f7g8h
                  us-east-2: vpc-9i8h7g6f5e4d3c2b
                  us-west-1: vpc-4d3c2b1a0f9e8d7
        ```

        For the regions without configured `vpc_ids`, enable default VPCs by setting `default_vpcs` to `true`.

??? info "Private subnets"
    By default, `dstack` provisions instances with public IPs and permits inbound SSH traffic.
    If you want `dstack` to use private subnets and provision instances without public IPs, set `public_ips` to `false`.

    ```yaml
    projects:
      - name: main
        backends:
          - type: aws
            creds:
              type: default

            public_ips: false
    ```
    
    Using private subnets assumes that both the `dstack` server and users can access the configured VPC's private subnets.
    Additionally, private subnets must have outbound internet connectivity provided by NAT Gateway, Transit Gateway, or other mechanism.

??? info "OS images"
    By default, `dstack` uses its own [AMI :material-arrow-top-right-thin:{ .external }](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AMIs.html)
    optimized for `dstack`.
    To use your own or other third-party images, set the `os_images` property:

    ```yaml
    projects:
      - name: main
        backends:
          - type: aws
            creds:
              type: default

            os_images:
              cpu:
                name: my-ami-for-cpu-instances
                owner: self
                user: dstack
              nvidia:
                name: 'Some ThirdParty CUDA image'
                owner: 123456789012
                user: ubuntu
    ```

    Here, both `cpu` and `nvidia` properties are optional, but if the property is not set, you won´t be able to use the corresponding instance types.

    The `name` is an AMI name.
    The `owner` is either an AWS account ID (a 12-digit number) or a special value `self` indicating the current account.
    The `user` specifies an OS user for instance provisioning.

    !!! info "Image requirements"
        * SSH server listening on port 22
        * `user` with passwordless sudo access
        * Docker is installed
        * (For NVIDIA instances) NVIDIA/CUDA drivers and NVIDIA Container Toolkit are installed

#### Azure

There are two ways to configure Azure: using a client secret or using the default credentials.

=== "Default credentials"

    If you have default credentials set up, configure the backend like this:

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

    If you don't know your `subscription_id` and `tenant_id`, use [Azure CLI :material-arrow-top-right-thin:{ .external }](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli):

    ```shell
    az account show --query "{subscription_id: id, tenant_id: tenantId}"
    ```

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

    If you don't know your `subscription_id`, use [Azure CLI :material-arrow-top-right-thin:{ .external }](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli):
    
    ```shell
    az account show --query "{subscription_id: id}"
    ```

??? info "Required permissions"
    The following Azure permissions are sufficient for `dstack` to work:

    ```json
    {
        "properties": {
            "roleName": "dstack-role",
            "description": "Minimal required permissions for using Azure with dstack",
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

??? info "VPC"
    By default, `dstack` creates new Azure networks and subnets for every configured region.
    It's possible to use custom networks by specifying `vpc_ids`:

    ```yaml
    projects:
      - name: main
        backends:
          - type: azure
            creds:
              type: default
        regions: [westeurope]
        vpc_ids:
          westeurope: myNetworkResourceGroup/myNetworkName
    ```


??? info "Private subnets"
    By default, `dstack` provisions instances with public IPs and permits inbound SSH traffic.
    If you want `dstack` to use private subnets and provision instances without public IPs,
    specify custom networks using `vpc_ids` and set `public_ips` to `false`.

    ```yaml
    projects:
      - name: main
        backends:
          - type: azure
            creds:
              type: default
            regions: [westeurope]
            vpc_ids:
              westeurope: myNetworkResourceGroup/myNetworkName
            public_ips: false
    ```
    
    Using private subnets assumes that both the `dstack` server and users can access the configured VPC's private subnets.
    Additionally, private subnets must have outbound internet connectivity provided by [NAT Gateway or other mechanism](https://learn.microsoft.com/en-us/azure/nat-gateway/nat-overview).

#### GCP

There are two ways to configure GCP: using a service account or using the default credentials.

=== "Default credentials"

    Enable GCP application default credentials:

    ```shell
    gcloud auth application-default login 
    ```

    Then configure the backend like this:

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

=== "Service account"

    To create a service account, follow [this guide :material-arrow-top-right-thin:{ .external }](https://cloud.google.com/iam/docs/service-accounts-create). After setting up the service account [create a key :material-arrow-top-right-thin:{ .external }](https://cloud.google.com/iam/docs/keys-create-delete) for it and download the corresponding JSON file.

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

If you don't know your GCP project ID, use [Google Cloud CLI :material-arrow-top-right-thin:{ .external }](https://cloud.google.com/sdk/docs/install-sdk):

```shell
gcloud projects list --format="json(projectId)"
```

??? info "Required permissions"
    The following GCP permissions are sufficient for `dstack` to work:

    ```
    compute.disks.create
    compute.disks.delete
    compute.disks.get
    compute.disks.list
    compute.disks.setLabels
    compute.disks.use
    compute.firewalls.create
    compute.images.useReadOnly
    compute.instances.attachDisk
    compute.instances.create
    compute.instances.delete
    compute.instances.detachDisk
    compute.instances.get
    compute.instances.setLabels
    compute.instances.setMetadata
    compute.instances.setTags
    compute.networks.get
    compute.networks.updatePolicy
    compute.regions.get
    compute.regions.list
    compute.routers.list
    compute.subnetworks.list
    compute.subnetworks.use
    compute.subnetworks.useExternalIp
    compute.zoneOperations.get
    ```

    If you plan to use TPUs, additional permissions are required:

    ```
    tpu.nodes.create
    tpu.nodes.delete
    tpu.nodes.get
    tpu.operations.get
    tpu.operations.list
    ```

    Also, the use of TPUs requires the `serviceAccountUser` role.
    For TPU VMs, dstack will use the default service account.

??? info "Required APIs"
    First, ensure the required APIs are enabled in your GCP `project_id`.

    ```shell
    PROJECT_ID=...
    gcloud config set project $PROJECT_ID
    gcloud services enable cloudapis.googleapis.com
    gcloud services enable compute.googleapis.com
    ```

??? info "VPC"

    === "VPC"
    
        <div editor-title="~/.dstack/server/config.yml">
    
        ```yaml
        projects:
        - name: main
          backends:
            - type: gcp
              project_id: gcp-project-id
              creds:
                type: default
    
              vpc_name: my-custom-vpc
        ```
    
        </div>
    
    === "Shared VPC"
    
        <div editor-title="~/.dstack/server/config.yml">
    
        ```yaml
        projects:
        - name: main
          backends:
            - type: gcp
              project_id: gcp-project-id
              creds:
                type: default
    
              vpc_name: my-custom-vpc
              vpc_project_id: another-project-id
        ```
    
        </div>
    
        To use a shared VPC, that VPC has to be configured with two additional firewall rules:
    
        * Allow `INGRESS` traffic on port `22`, with the target tag `dstack-runner-instance`
        * Allow `INGRESS` traffic on ports `22`, `80`, `443`, with the target tag `dstack-gateway-instance`

??? info "Private subnets"
    By default, `dstack` provisions instances with public IPs and permits inbound SSH traffic.
    If you want `dstack` to use private subnets and provision instances without public IPs, set `public_ips` to `false`.

    ```yaml
    projects:
      - name: main
        backends:
          - type: gcp
            creds:
              type: default

            public_ips: false
    ```
    
    Using private subnets assumes that both the `dstack` server and users can access the configured VPC's private subnets.
    Additionally, [Cloud NAT](https://cloud.google.com/nat/docs/overview) must be configured to provide access to external resources for provisioned instances.

#### Lambda

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

#### RunPod

Log into your [RunPod :material-arrow-top-right-thin:{ .external }](https://www.runpod.io/console/) console, click Settings in the sidebar, expand the `API Keys` section, and click
the button to create a Read & Write key.

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

#### Vast.ai

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

Also, the `vastai` backend supports on-demand instances only. Spot instance support coming soon.

#### TensorDock

Log into your [TensorDock :material-arrow-top-right-thin:{ .external }](https://dashboard.tensordock.com/) account, click Developers in the sidebar, and use the `Create an Authorization` section to create a new authorization key.

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

The `tensordock` backend supports on-demand instances only. Spot instance support coming soon.

#### CUDO

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

#### OCI

There are two ways to configure OCI: using client credentials or using the default credentials.

=== "Default credentials"
    If you have default credentials set up in `~/.oci/config`, configure the backend like this:

    <div editor-title="~/.dstack/server/config.yml">

    ```yaml
    projects:
    - name: main
      backends:
      - type: oci
        creds:
          type: default
    ```

    </div>

=== "Client credentials"

    Log into the [OCI Console :material-arrow-top-right-thin:{ .external }](https://cloud.oracle.com), go to `My profile`, 
    select `API keys`, and click `Add API key`.

    Once you add a key, you'll see the configuration file. Copy its values to configure the backend as follows:

    <div editor-title="~/.dstack/server/config.yml">
    
    ```yaml
    projects:
    - name: main
      backends:
      - type: oci
        creds:
          type: client
          user: ocid1.user.oc1..g5vlaeqfu47akmaafq665xsgmyaqjktyfxtacfxc4ftjxuca7aohnd2ev66m
          tenancy: ocid1.tenancy.oc1..ajqsftvk4qarcfaak3ha4ycdsaahxmaita5frdwg3tqo2bcokpd3n7oizwai
          region: eu-frankfurt-1
          fingerprint: 77:32:77:00:49:7c:cb:56:84:75:8e:77:96:7d:53:17
          key_file: ~/.oci/private_key.pem
    ```
    
    </div>

    Make sure to include either the path to your private key via `key_file` or the contents of the key via `key_content`.

??? info "Required permissions"

    This is an example of a restrictive policy for a group of `dstack` users:

    ```
    Allow group <dstack-users> to read compartments in tenancy where target.compartment.name = '<dstack-compartment>'
    Allow group <dstack-users> to read marketplace-community-listings in compartment <dstack-compartment>
    Allow group <dstack-users> to manage app-catalog-listing in compartment <dstack-compartment>
    Allow group <dstack-users> to manage instances in compartment <dstack-compartment>
    Allow group <dstack-users> to manage compute-capacity-reports in compartment <dstack-compartment>
    Allow group <dstack-users> to manage volumes in compartment <dstack-compartment>
    Allow group <dstack-users> to manage volume-attachments in compartment <dstack-compartment>
    Allow group <dstack-users> to manage virtual-network-family in compartment <dstack-compartment>
    ```

    To use this policy, create a compartment for `dstack` and specify it in `~/.dstack/server/config.yml`.

    ```yaml
    projects:
    - name: main
      backends:
      - type: oci
        creds:
          type: default
        compartment_id: ocid1.compartment.oc1..aaaaaaaa
    ```

#### DataCrunch

Log into your [DataCrunch :material-arrow-top-right-thin:{ .external }](https://cloud.datacrunch.io/) account, click Keys in the sidebar, find `REST API Credentials` area and then click the `Generate Credentials` button.

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

### On-prem servers

#### SSH fleets

For using `dstack` with on-prem servers, no backend configuration is required.
See [SSH fleets](../../concepts/fleets.md#ssh-fleets) for more details.

#### Kubernetes

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

    ??? info "Kind"
        If you are using [Kind](https://kind.sigs.k8s.io/), make sure to make 
        to set up `ssh_port` via `extraPortMappings` for proxying SSH traffic:
    
        ```yaml
        kind: Cluster
        apiVersion: kind.x-k8s.io/v1alpha4
        nodes:
          - role: control-plane
            extraPortMappings:
              - containerPort: 32000 # Must be same as `ssh_port`
                hostPort: 32000 # Must be same as `ssh_port`
        ```
    
        Go ahead and create the cluster like this: 

        ```shell
        kind create cluster --config examples/misc/kubernetes/kind-config.yml
        ```

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

    ??? info "EKS"
        For example, if you are using EKS, make sure to add it via an ingress rule
        of the corresponding security group:
    
        ```shell
        aws ec2 authorize-security-group-ingress --group-id <cluster-security-group-id> --protocol tcp --port 32000 --cidr 0.0.0.0/0
        ```

[//]: # (TODO: Elaborate on gateways, and what backends allow configuring them)

[//]: # (TODO: Should we automatically detect ~/.kube/config)

??? info "NVIDIA GPU Operator"
    To use GPUs with Kubernetes, the cluster must be installed with the
    [NVIDIA GPU Operator :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/index.html).

    [//]: # (TODO: Provide short yet clear instructions. Elaborate on whether it works with Kind.)

## Encryption

By default, `dstack` stores data in plaintext. To enforce encryption, you 
specify one or more encryption keys.

`dstack` currently supports AES and identity (plaintext) encryption keys.
Support for external providers like HashiCorp Vault and AWS KMS is planned.

=== "AES"
    The `aes` encryption key encrypts data using [AES-256](https://en.wikipedia.org/wiki/Advanced_Encryption_Standard) in GCM mode.
    To configure the `aes` encryption, generate a random 32-byte key:

    <div class="termy">
    
    ```shell
    $ head -c 32 /dev/urandom | base64
    
    opmx+r5xGJNVZeErnR0+n+ElF9ajzde37uggELxL
    ```

    </div>
    
    And specify it as `secret`:
    
    ```yaml
    encryption:
      keys:
        - type: aes
          name: key1
          secret: opmx+r5xGJNVZeErnR0+n+ElF9ajzde37uggELxL
    ```

=== "Identity"
    The `identity` encryption performs no encryption and stores data in plaintext.
    You can specify an `identity` encryption key explicitly if you want to decrypt the data:
    
    ```yaml
    encryption:
      keys:
      - type: identity
      - type: aes
        name: key1
        secret: opmx+r5xGJNVZeErnR0+n+ElF9ajzde37uggELxL
    ```
    
    With this configuration, the `aes` key will still be used to decrypt the old data,
    but new writes will store the data in plaintext.

??? info "Key rotation"
    If multiple keys are specified, the first is used for encryption, and all are tried for decryption. This enables key
    rotation by specifying a new encryption key.
    
    ```yaml
    encryption:
      keys:
      - type: aes
        name: key2
        secret: cR2r1JmkPyL6edBQeHKz6ZBjCfS2oWk87Gc2G3wHVoA=

      - type: aes
        name: key1
        secret: E5yzN6V3XvBq/f085ISWFCdgnOGED0kuFaAkASlmmO4=
    ```
    
    Old keys may be deleted once all existing records have been updated to re-encrypt sensitive data. 
    Encrypted values are prefixed with key names, allowing DB admins to identify the keys used for encryption.

[//]: # (## Default permissions)

[//]: # (`dstack` supports changing default permissions. For example, by default all users)
[//]: # (can create and manage their own projects. You can specify `default_permissions`)
[//]: # (so that only global admins can create and manage projects:)

[//]: # (<div editor-title="~/.dstack/server/config.yml">)

[//]: # (```yaml)
[//]: # (default_permissions:)
[//]: # (  allow_non_admins_create_projects: false)
[//]: # (```)

[//]: # (</div>)

See the [reference table](#default-permissions) for all configurable permissions.

## Root reference

#SCHEMA# dstack._internal.server.services.config.ServerConfig
    overrides:
      show_root_heading: false

## `projects[n]` { #_projects data-toc-label="projects" }

#SCHEMA# dstack._internal.server.services.config.ProjectConfig
    overrides:
        show_root_heading: false
        backends:
            type: 'Union[AWSConfigInfoWithCreds, AzureConfigInfoWithCreds, GCPConfigInfoWithCreds, LambdaConfigInfoWithCreds, TensorDockConfigInfoWithCreds, VastAIConfigInfoWithCreds, KubernetesConfig]'

## `projects[n].backends[type=aws]` { #_aws data-toc-label="backends[type=aws]" }

#SCHEMA# dstack._internal.server.services.config.AWSConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: aws-

## `projects[n].backends[type=aws].creds` { #_aws-creds data-toc-label="backends[type=aws].creds" }

=== "Access key"
    #SCHEMA# dstack._internal.core.models.backends.aws.AWSAccessKeyCreds
        overrides:
            show_root_heading: false
            type:
                required: true

=== "Default"
    #SCHEMA# dstack._internal.core.models.backends.aws.AWSDefaultCreds
        overrides:
            show_root_heading: false
            type:
                required: true

## `projects[n].backends[type=aws].os_images` { #_aws-os-images data-toc-label="backends[type=aws].os_images" }

#SCHEMA# dstack._internal.core.models.backends.aws.AWSOSImageConfig
    overrides:
        show_root_heading: false
        type:
            required: true

## `projects[n].backends[type=aws].os_images.*` { #_aws-os-image data-toc-label="backends[type=aws].os_images.*" }

#SCHEMA# dstack._internal.core.models.backends.aws.AWSOSImage
    overrides:
        show_root_heading: false
        type:
            required: true

## `projects[n].backends[type=azure]` { #_azure data-toc-label="backends[type=azure]" }

#SCHEMA# dstack._internal.server.services.config.AzureConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: azure-

## `projects[n].backends[type=azure].creds` { #_azure-creds data-toc-label="backends[type=azure].creds" }

=== "Client"
    #SCHEMA# dstack._internal.core.models.backends.azure.AzureClientCreds
        overrides:
            show_root_heading: false
            type:
                required: true

=== "Default"
    #SCHEMA# dstack._internal.core.models.backends.azure.AzureDefaultCreds
        overrides:
            show_root_heading: false
            type:
                required: true

## `projects[n].backends[type=datacrunch]` { #_datacrunch data-toc-label="backends[type=datacrunch]" }

#SCHEMA# dstack._internal.server.services.config.DataCrunchConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: datacrunch-

## `projects[n].backends[type=datacrunch].creds` { #_datacrunch-creds data-toc-label="backends[type=datacrunch].creds" }

#SCHEMA# dstack._internal.core.models.backends.datacrunch.DataCrunchAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

## `projects[n].backends[type=gcp]` { #_gcp data-toc-label="backends[type=gcp]" }

#SCHEMA# dstack._internal.server.services.config.GCPConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: gcp-

## `projects[n].backends[type=gcp].creds` { #_gcp-creds data-toc-label="backends[type=gcp].creds" }

=== "Service account"
    #SCHEMA# dstack._internal.server.services.config.GCPServiceAccountCreds
        overrides:
            show_root_heading: false
            type:
                required: true

    ??? info "Specifying `data`"
        To specify service account file contents as a string, use `jq`:

        ```shell
        cat my-service-account-file.json | jq -c | jq -R
        ```

=== "Default"
    #SCHEMA# dstack._internal.server.services.config.GCPDefaultCreds
        overrides:
            show_root_heading: false
            type:
                required: true

## `projects[n].backends[type=lambda]` { #_lambda data-toc-label="backends[type=lambda]" }

#SCHEMA# dstack._internal.server.services.config.LambdaConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: lambda-

## `projects[n].backends[type=lambda].creds` { #_lambda-creds data-toc-label="backends[type=lambda].creds" }

#SCHEMA# dstack._internal.core.models.backends.lambdalabs.LambdaAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

## `projects[n].backends[type=oci]` { #_oci data-toc-label="backends[type=oci]" }

#SCHEMA# dstack._internal.server.services.config.OCIConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: oci-

## `projects[n].backends[type=oci].creds` { #_oci-creds data-toc-label="backends[type=oci].creds" }

=== "Client"
    #SCHEMA# dstack._internal.core.models.backends.oci.OCIClientCreds
        overrides:
            show_root_heading: false
            type:
                required: true

=== "Default"
    #SCHEMA# dstack._internal.core.models.backends.oci.OCIDefaultCreds
        overrides:
            show_root_heading: false
            type:
                required: true

## `projects[n].backends[type=tensordock]` { #_tensordock data-toc-label="backends[type=tensordock]" }

#SCHEMA# dstack._internal.server.services.config.TensorDockConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: tensordock-

## `projects[n].backends[type=tensordock].creds` { #_tensordock-creds data-toc-label="backends[type=tensordock].creds" }

#SCHEMA# dstack._internal.core.models.backends.tensordock.TensorDockAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

## `projects[n].backends[type=vastai]` { #_vastai data-toc-label="backends[type=vastai]" }

#SCHEMA# dstack._internal.server.services.config.VastAIConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: vastai-

## `projects[n].backends[type=vastai].creds` { #_vastai-creds data-toc-label="backends[type=vastai].creds" }

#SCHEMA# dstack._internal.core.models.backends.vastai.VastAIAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

## `projects[n].backends[type=cudo]` { #_cudo data-toc-label="backends[type=cudo]" }

#SCHEMA# dstack._internal.server.services.config.CudoConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: cudo-

## `projects[n].backends[type=cudo].creds` { #_cudo-creds data-toc-label="backends[type=cudo].creds" }

#SCHEMA# dstack._internal.core.models.backends.cudo.CudoAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

## `projects[n].backends[type=kubernetes]` { #_kubernetes data-toc-label="backends[type=kubernetes]" }

#SCHEMA# dstack._internal.server.services.config.KubernetesConfig
    overrides:
        show_root_heading: false
        type:
            required: true

## `projects[n].backends[type=kubernetes].kubeconfig` { #_kubeconfig data-toc-label="kubeconfig" }

##SCHEMA# dstack._internal.server.services.config.KubeconfigConfig
    overrides:
        show_root_heading: false

??? info "Specifying `data`"
    To specify service account file contents as a string, use `jq`:

    ```shell
    cat my-service-account-file.json | jq -c | jq -R
    ```

## `projects[n].backends[type=kubernetes].networking` { #_networking data-toc-label="networking" }

##SCHEMA# dstack._internal.core.models.backends.kubernetes.KubernetesNetworkingConfig
    overrides:
        show_root_heading: false

## `encryption` { #_encryption data-toc-label="encryption" }

#SCHEMA# dstack._internal.server.services.config.EncryptionConfig
    overrides:
        show_root_heading: false

## `encryption.keys[n][type=identity]` { #_encryption-keys-identity data-toc-label="encryption.keys.identity" }

#SCHEMA# dstack._internal.server.services.encryption.keys.identity.IdentityEncryptionKeyConfig
    overrides:
        show_root_heading: false
        type:
            required: true

## `encryption.keys[n][type=aes]` { #_encryption-keys-aes data-toc-label="encryption.keys.aes" }

#SCHEMA# dstack._internal.server.services.encryption.keys.aes.AESEncryptionKeyConfig
    overrides:
        show_root_heading: false
        type:
            required: true

## `default_permissions` { #_default-permissions data-toc-label="default-permissions" }

#SCHEMA# dstack._internal.server.services.permissions.DefaultPermissions
    overrides:
        show_root_heading: false
