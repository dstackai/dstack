To run, you need to specify AWS credentials in ENV

## Build Ubuntu AMI (with CUDA)
```shell
packer build packer.json
```

# Azure

## Allocate resources (make credentials)

Follow [installation instruction](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-linux?pivots=apt)
for Azure CLI `az`. [Login](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli) for managing resources:

```commandline
$ az login
```

Steps below follows [HOWTO](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/build-image-with-packer).
Create group as container for result image. Value `packer` is from property `managed_image_resource_group_name` of
`azure-arm` packer's builder. Value `eastus` is property `location` of `azure-arm` (Azure has two kind notation for
the same location).

```commandline
$ az group create -n packer -l eastus
```

Packer allocates resources on its own. It requires access to subscription. Obtain id.

```commandline
$ az account show --query "{ subscription_id: id }"
{
  "subscription_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx"
}
```

Create credentials for packer.

```commandline
$ az ad sp create-for-rbac --role Contributor --scopes /subscriptions/<subscription_id> --query "{ client_id: appId, client_secret: password, tenant_id: tenant }"
{
    "client_id": "f5b6a5cf-fbdf-4a9f-b3b8-3c2cd00225a4",
    "client_secret": "0e760437-bf34-4aad-9f8d-870be799c55d",
    "tenant_id": "72f988bf-86f1-41af-91ab-2d7cd011db47"
}
```

Set environment variables.

| Env | Azure |
|-----|-------|
| AZURE_CLIENT_ID | client_id |
| AZURE_CLIENT_SECRET | client_secret |
| AZURE_TENANT_ID | tenant_id |
| AZURE_SUBSCRIPTION_ID | subscription_id |

# Nebius

## Setup Nebius credentials

> `compute.admin` is not sufficient for packer. Use `admin` role instead.

```shell
ncp config profile create packer
ncp config set service-account-key path/to/service_account.json
ncp config set endpoint api.ai.nebius.cloud:443
export PKR_VAR_nebius_token=$(ncp iam create-token)
```

## Build images

```shell
export PKR_VAR_nebius_folder_id=...
export PKR_VAR_nebius_subnet_id=...
# no CUDA
packer build -only yandex.nebius -var image_version=0.4rc3 .
# with CUDA
packer build -only yandex.nebius-cuda -var image_version=0.4rc3 .
```
