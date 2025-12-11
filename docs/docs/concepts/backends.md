# Backends

Backends allow `dstack` to provision fleets across cloud providers or Kubernetes clusters.

`dstack` supports two types of backends: 

  * [VM-based](#vm-based) – use `dstack`'s native integration with cloud providers to provision VMs, manage clusters, and orchestrate container-based runs.  
  * [Container-based](#container-based) – use either `dstack`'s native integration with cloud providers or Kubernetes to orchestrate container-based runs; provisioning in this case is delegated to the cloud provider or Kubernetes.  

??? info "SSH fleets"
    When using `dstack` with on-prem servers, backend configuration isn’t required. Simply create [SSH fleets](../concepts/fleets.md#ssh-fleets) once the server is up.

Backends can be configured via `~/.dstack/server/config.yml` or through the [project settings page](../concepts/projects.md#backends) in the UI. See the examples of backend configuration below.

## VM-based

VM-based backends allow `dstack` users to manage clusters and orchestrate container-based runs across a wide range of cloud providers.  
Under the hood, `dstack` uses native integrations with these providers to provision clusters on demand.  

Compared to [container-based](#container-based) backends, this approach offers finer-grained, simpler control over cluster provisioning and eliminates the dependency on a Kubernetes layer.

<!-- TODO: Mention how VM-based backends are better than Kubernetes -->

### AWS

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
            },
            {
                "Effect": "Allow",
                "Action": [
                    "iam:GetInstanceProfile",
                    "iam:GetRole",
                    "iam:PassRole"
                ],
                "Resource": "*"
            }
        ]
    }
    ```

    The `elasticloadbalancing:*` and `acm:*` permissions are only needed for provisioning gateways with ACM (AWS Certificate Manager) certificates.

    The `iam:*` permissions are only needed if you specify `iam_instance_profile` to assign to EC2 instances.

    You can also limit permissions to specific resources in your account:
    
    ```
    {
        "Version": "2012-10-17",
        "Statement": [
            ...
            {
                "Effect": "Allow",
                "Action": [
                    "iam:GetInstanceProfile",
                    "iam:GetRole",
                    "iam:PassRole"
                ],
                "Resource": "arn:aws:iam::account-id:role/EC2-roles-for-XYZ-*"
            }
        ]
    }
    ```

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
    By default, `dstack` uses its own [AMI](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AMIs.html)
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
        * The firewall (`iptables`, `ufw`, etc.) must allow external traffic to port 22 and all traffic within the private subnet, and should forbid any other incoming external traffic.

### Azure

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

    If you don't know your `subscription_id` and `tenant_id`, use [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli):

    ```shell
    az account show --query "{subscription_id: id, tenant_id: tenantId}"
    ```

=== "Client secret"

    A client secret can be created using the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli):

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

    If you don't know your `subscription_id`, use [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli):
    
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
                    "Microsoft.ManagedIdentity/userAssignedIdentities/assign/action",
                    "Microsoft.ManagedIdentity/userAssignedIdentities/read",
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

    The `"Microsoft.Resources/subscriptions/resourceGroups/write"` permission is not required
    if [`resource_group`](/docs/reference/server/config.yml/#azure) is specified.

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

### GCP

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

    To create a service account, follow [this guide](https://cloud.google.com/iam/docs/service-accounts-create). After setting up the service account [create a key](https://cloud.google.com/iam/docs/keys-create-delete) for it and download the corresponding JSON file.

    Then go ahead and configure the backend by specifying the downloaded file path.

    <div editor-title="~/.dstack/server/config.yml">

    ```yaml
    projects:
    - name: main
      backends:
        - type: gcp
          project_id: my-gcp-project
          creds:
            type: service_account
            filename: ~/.dstack/server/gcp-024ed630eab5.json
    ```

    </div>

    ??? info "User interface"
        If you are configuring the `gcp` backend on the [project settigns page](projects.md#backends), 
        specify the contents of the JSON file in `data`:

        <div editor-title="~/.dstack/server/config.yml">

        ```yaml
        type: gcp
        project_id: my-gcp-project
        creds:
          type: service_account
          data: |
            {
              "type": "service_account",
              "project_id": "my-gcp-project",
              "private_key_id": "abcd1234efgh5678ijkl9012mnop3456qrst7890",
              "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEv...rest_of_key...IDAQAB\n-----END PRIVATE KEY-----\n",
              "client_email": "my-service-account@my-gcp-project.iam.gserviceaccount.com",
              "client_id": "123456789012345678901",
              "auth_uri": "https://accounts.google.com/o/oauth2/auth",
              "token_uri": "https://oauth2.googleapis.com/token",
              "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
              "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/my-service-account%40my-gcp-project.iam.gserviceaccount.com",
              "universe_domain": "googleapis.com"
            }
        ```

        </div>

If you don't know your GCP project ID, use [Google Cloud CLI](https://cloud.google.com/sdk/docs/install-sdk):

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
    compute.instances.setServiceAccount
    compute.instances.setTags
    compute.networks.get
    compute.networks.updatePolicy
    compute.regions.get
    compute.regions.list
    compute.reservations.list
    compute.resourcePolicies.create
    compute.resourcePolicies.delete
    compute.routers.list
    compute.subnetworks.list
    compute.subnetworks.use
    compute.subnetworks.useExternalIp
    compute.zoneOperations.get
    ```

    If you plan to use TPUs, additional permissions are required:

    ```
    tpu.nodes.create
    tpu.nodes.get
    tpu.nodes.update
    tpu.nodes.delete
    tpu.operations.get
    tpu.operations.list
    ```

    Also, the use of TPUs requires the `serviceAccountUser` role.
    For TPU VMs, dstack will use the default service account.

    If you plan to use shared reservations, the `compute.reservations.list`
    permission is required in the project that owns the reservations.

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

        If you specify a non-default VPC, ensure it has a firewall rule
        allowing all traffic within the VPC. This is needed for multi-node tasks to work.
        The default VPC already permits traffic within the VPC.

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

        When using a Shared VPC, ensure there is a firewall rule allowing `INGRESS` traffic on port `22`.
        You can limit this rule to `dstack` instances using the `dstack-runner-instance` target tag.

        When using GCP gateways with a Shared VPC, also ensure there is a firewall rule allowing `INGRESS` traffic on ports `22`, `80`, `443`.
        You can limit this rule to `dstack` gateway instances using the `dstack-gateway-instance` target tag.

        To use TPUs with a Shared VPC, you need to grant the TPU Service Account in your service project permissions
        to manage resources in the host project by granting the "TPU Shared VPC Agent" (roles/tpu.xpnAgent) role
        ([more in the GCP docs](https://cloud.google.com/tpu/docs/shared-vpc-networks#vpc-shared-vpc)).

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

### Nebius

Log into your [Nebius AI Cloud](https://console.eu.nebius.com/) account, navigate to Access, and select Service Accounts. Create a service account, add it to the editors group, and upload its authorized key.

Then configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: nebius
    creds:
      type: service_account
      service_account_id: serviceaccount-e00dhnv9ftgb3cqmej
      public_key_id: publickey-e00ngaex668htswqy4
      private_key_file: ~/path/to/key.pem
```

</div>

??? info "Credentials file"
    It's also possible to configure the `nebius` backend using a credentials file [generated](https://docs.nebius.com/iam/service-accounts/authorized-keys#create) by the `nebius` CLI:

    <div class="termy">

    ```shell
    $ nebius iam auth-public-key generate \
        --service-account-id <service account ID> \
        --output ~/.nebius/sa-credentials.json
    ```
    
    </div>

  
    ```yaml
    projects:
    - name: main
      backends:
      - type: nebius
        creds:
          type: service_account
          filename: ~/.nebius/sa-credentials.json
    ```

??? info "User interface"
    If you are configuring the `nebius` backend on the [project settigns page](projects.md#backends), 
    specify the contents of the private key file in `private_key_content`:

    <div editor-title="~/.dstack/server/config.yml">

    ```yaml
    type: nebius
    creds:
      type: service_account
      service_account_id: serviceaccount-e00dhnv9ftgb3cqmej
      public_key_id: publickey-e00ngaex668htswqy4
      private_key_content: |
        -----BEGIN PRIVATE KEY-----
        MIIJQQIBADANBgkqhkiG9w0BAQEFAASCCSswggknAgEAAoICAQChwQ5OOhy60N7m
        cPx/9M0oRUyJdRRv2nCALbdU/wSDOo8o5N7sP63zCaxXPeKwLNEzneMd/U0gWSv2
        [...]
        8y1qYDPKQ8LR+DPCUmyhM2I8t6673Vz3GrtEjkLhgQo/KqOVb3yiBFVfkA5Jov5s
        kO7y4T0ynsI8b6wlhCukQTLpIYJ5
        -----END PRIVATE KEY-----
    ```

    </div>

??? info "Projects"
    If you have multiple projects per region, specify which ones to use, at most one per region.

    <div editor-title="~/.dstack/server/config.yml">

    ```yaml
    type: nebius
    projects:
    - project-e00jt6t095t1ahrg4re30
    - project-e01iahuh3cklave4ao1nv
    creds:
      type: service_account
      service_account_id: serviceaccount-e00dhnv9ftgb3cqmej
      public_key_id: publickey-e00ngaex668htswqy4
      private_key_file: ~/path/to/key.pem
    ```

    </div>

!!! info "Python version"
    Nebius is only supported if `dstack server` is running on Python 3.10 or higher.


### Vultr

Log into your [Vultr](https://www.vultr.com/) account, click `Account` in the sidebar, select `API`, find the `Personal Access Token` panel and click the `Enable API` button. In the `Access Control` panel, allow API requests from all addresses or from the subnet where your `dstack` server is deployed.

Then, go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
  - name: main
    backends:
      - type: vultr
        creds:
          type: api_key
          api_key: B57487240a466624b48de22865589
```

</div>

### CUDO

Log into your [CUDO Compute](https://compute.cudo.org/) account, click API keys in the sidebar, and click the `Create an API key` button.

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

### OCI

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

    Log into the [OCI Console](https://cloud.oracle.com), go to `My profile`, 
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

<span id="datacrunch"></span>

### Verda (formerly DataCrunch) { #verda }

Log into your [Verda](https://console.verda.com/signin) account, click Keys in the sidebar, find `REST API Credentials` area and then click the `Generate Credentials` button.

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

### AMD Developer Cloud
Log into your [AMD Developer Cloud](https://amd.digitalocean.com/login) account. Click `API` in the sidebar and click the button `Generate New Token`. 

Then, go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
    - type: amddevcloud
      project_name: my-amd-project
      creds:
        type: api_key
        api_key: ...
```

</div>

??? info "Project"
    If `project_name` is not set, the default project will be used.

??? info "Required permissions"
    The API key must have the following scopes assigned:

    * `account` - read
    * `droplet` - create, read, update, delete, admin
    * `project` - create, read, update, delete
    * `regions` - read
    * `sizes` - read
    * `ssh_key` - create, read, update, delete


### Digital Ocean
Log into your [Digital Ocean](https://cloud.digitalocean.com/login) account. Click `API` in the sidebar and click the button `Generate New Token`. 

Then, go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
    - type: digitalocean
      project_name: my-digital-ocean-project
      creds:
        type: api_key
        api_key: ...
```

</div>

??? info "Project"
    If `project_name` is not set, the default project will be used.

??? info "Required permissions"
    The API key must have the following scopes assigned:

    * `account` - read
    * `droplet` - create, read, update, delete, admin
    * `project` - create, read, update, delete
    * `regions` - read
    * `sizes` - read
    * `ssh_key` - create, read, update,delete

### Hot Aisle

Log in to the SSH TUI as described in the [Hot Aisle Quick Start](https://hotaisle.xyz/quick-start/).
Create a new team and generate an API key for the member in the team.

Then, go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
    - type: hotaisle
      team_handle: hotaisle-team-handle
      creds:
        type: api_key
        api_key: 9c27a4bb7a8e472fae12ab34.3f2e3c1db75b9a0187fd2196c6b3e56d2b912e1c439ba08d89e7b6fcd4ef1d3f
```

</div>

??? info "Required permissions"
    The API key must have the following roles assigned:

    * **Owner role for the user** - Required for creating and managing SSH keys
    * **Operator role for the team** - Required for managing virtual machines within the team


### CloudRift

Log into your [CloudRift](https://console.cloudrift.ai/) console, click `API Keys` in the sidebar and click the button to create a new API key.

Ensure you've created a project with CloudRift.

Then proceed to configuring the backend.

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
  - name: main
    backends:
      - type: cloudrift
        creds:
          type: api_key
          api_key: rift_2prgY1d0laOrf2BblTwx2B2d1zcf1zIp4tZYpj5j88qmNgz38pxNlpX3vAo
```

</div>

## Container-based

Container-based backends allow `dstack` to orchestrate container-based runs either directly on cloud providers that support containers or on Kubernetes.  
In this case, `dstack` delegates provisioning to the cloud provider or Kubernetes.

Compared to [VM-based](#vm-based) backends, they offer less fine-grained control over provisioning but rely on the native logic of the underlying environment, whether that’s a cloud provider or Kubernetes.

<!-- TODO: Explain what features aren't supported with container-based backends, such as idle_duration, min and target number of nodes when fleet provisioning, instance volumes, Docker-in-Docker, etc. -->

### Kubernetes

Regardless of whether it’s on-prem Kubernetes or managed, `dstack` can orchestrate container-based runs across your clusters.

To use the `kubernetes` backend with `dstack`, you need to configure it with the path to the kubeconfig file, the IP address of any node in the cluster, and the port that `dstack` will use for proxying SSH traffic. 

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
    backends:
    - type: kubernetes
      kubeconfig:
        filename: ~/.kube/config
      proxy_jump:
        hostname: 204.12.171.137
        port: 32000
```

</div>

??? info "Proxy jump"
    To allow the `dstack` server and CLI to access runs via SSH, `dstack` requires a node that acts as a jump host to proxy SSH traffic into containers.  

    To configure this node, specify `hostname` and `port` under the `proxy_jump` property:  

    - `hostname` — the IP address of any cluster node selected as the jump host. Both the `dstack` server and CLI must be able to reach it. This node can be either a GPU node or a CPU-only node — it makes no difference.  
    - `port` — any accessible port on that node, which `dstack` uses to forward SSH traffic.  

    No additional setup is required — `dstack` configures and manages the proxy automatically.

??? info "NVIDIA GPU Operator"
    For `dstack` to correctly detect GPUs in your Kubernetes cluster, the cluster must have the
    [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/index.html) pre-installed.

<!-- ??? info "Managed Kubernetes"
    While `dstack` supports both managed and on-prem Kubernetes clusters, it can only run on pre-provisioned nodes.
    Support for auto-scalable Kubernetes clusters is coming soon—you can track progress in the corresponding [issue](https://github.com/dstackai/dstack/issues/3126).
    
    If on-demand provisioning is important, we recommend using [VM-based](#vm-based) backends as they already support auto-scaling. -->

??? info "Required permissions"
    The following Kubernetes permissions are sufficient for `dstack` to work:

    ```yaml
    apiVersion: rbac.authorization.k8s.io/v1
    kind: ClusterRole
    metadata:
      name: dstack-backend
    rules:
    - apiGroups: [""]
      resources: ["namespaces"]
      verbs: ["get", "create"]
    - apiGroups: [""]
      resources: ["pods"]
      verbs: ["get", "create", "delete"]
    - apiGroups: [""]
      resources: ["services"]
      verbs: ["get", "create", "delete"]
    - apiGroups: [""]
      resources: ["nodes"]
      verbs: ["list"]
    ```
    
    Ensure you've created a ClusterRoleBinding to grant the role to the user or the service account you're using.

> To learn more, see the [Kubernetes](../guides/kubernetes.md) guide.

### RunPod

Log into your [RunPod](https://www.runpod.io/console/) console, click Settings in the sidebar, expand the `API Keys` section, and click
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

??? info "Community Cloud"
    By default, `dstack` considers instance offers from both the Secure Cloud and the
    [Community Cloud](https://docs.runpod.io/references/faq/#secure-cloud-vs-community-cloud).

    You can tell them apart by their regions.
    Secure Cloud regions contain datacenter IDs such as `CA-MTL-3`.
    Community Cloud regions contain country codes such as `CA`.

    <div class="termy">

    ```shell
    $ dstack apply -f .dstack.yml -b runpod

     #  BACKEND  REGION    INSTANCE               SPOT  PRICE
     1  runpod   CA        NVIDIA A100 80GB PCIe  yes   $0.6
     2  runpod   CA-MTL-3  NVIDIA A100 80GB PCIe  yes   $0.82
    ```

    </div>

    If you don't want to use the Community Cloud, set `community_cloud: false` in the backend settings.

    <div editor-title="~/.dstack/server/config.yml">

    ```yaml
    projects:
      - name: main
        backends:
          - type: runpod
            creds:
              type: api_key
              api_key: US9XTPDIV8AR42MMINY8TCKRB8S4E7LNRQ6CAUQ9
            community_cloud: false
    ```

    </div>

### Vast.ai

Log into your [Vast.ai](https://cloud.vast.ai/) account, click Account in the sidebar, and copy your
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

SSH fleets support the same features as [VM-based](#vm-based) backends.

!!! info "What's next"
    1. See the [`~/.dstack/server/config.yml`](../reference/server/config.yml.md) reference
    2. Check [Projects](../concepts/projects.md)
