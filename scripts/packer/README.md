# Packer templates for `dstack` VM images

This directory contains HashiCorp Packer templates for building VM images that are then used by `dstack` when running instances on some of the VM-based backends. While `dstack` uses standard OS images for some backends, backends with custom-built images have an advantage because these images are optimized for `dstack`, e.g. they contain pre-pulled `dstack` Docker images, which reduces the startup time of `dstack` jobs.

For most backends, we build two images: one for CPU-only instances, typically published as `dstack-X.Y`, and one for NVIDIA GPU instances, typically published as `dstack-cuda-X.Y`, where `X.Y` is the image version. Some backends may have additional images, e.g. Azure has `dstack-grid-X.Y` for instances requiring NVIDIA Grid drivers.

## Builds

Production builds are triggered manually in GitHub Actions, see `.github/workflows/docker.yml`.

The GitHub Actions workflow also allows for staging builds. Staging builds are more limited than production builds, e.g. the resulting image can be restricted to a single region and not made public, but this is usually sufficient for testing.

If you still need to build the images locally, see the GitHub Actions workflow for examples of how to use the packer templates. Additional instructions for some backends are provided below.

### Azure

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
