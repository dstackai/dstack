# ~/.dstack/server/config.yml

The `~/.dstack/server/config.yml` file is used
to configure [backends](../../concepts/backends.md) and other [sever-level settings](../../guides/server-deployment.md).

## Root reference

#SCHEMA# dstack._internal.server.services.config.ServerConfig
    overrides:
      show_root_heading: false

### `projects[n]` { #projects data-toc-label="projects" }

#SCHEMA# dstack._internal.server.services.config.ProjectConfig
    overrides:
        show_root_heading: false
        backends:
            type: 'Union[AWSConfigInfoWithCreds, AzureConfigInfoWithCreds, GCPConfigInfoWithCreds, LambdaConfigInfoWithCreds, NebiusConfigInfoWithCreds, RunpodConfigInfoWithCreds, TensorDockConfigInfoWithCreds, VastAIConfigInfoWithCreds, KubernetesConfig]'

#### `projects[n].backends` { #backends data-toc-label="backends" }

##### `projects[n].backends[type=aws]` { #aws data-toc-label="aws" }

#SCHEMA# dstack._internal.server.services.config.AWSConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: aws-

###### `projects[n].backends[type=aws].creds` { #aws-creds data-toc-label="creds" }

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

###### `projects[n].backends[type=aws].os_images` { #aws-os_images data-toc-label="os_images" }

#SCHEMA# dstack._internal.core.models.backends.aws.AWSOSImageConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: aws-os_images-

###### `projects[n].backends[type=aws].os_images.cpu` { #aws-os_images-cpu data-toc-label="cpu" }

#SCHEMA# dstack._internal.core.models.backends.aws.AWSOSImage
    overrides:
        show_root_heading: false
        type:
            required: true

###### `projects[n].backends[type=aws].os_images.nvidia` { #aws-os_images-nvidia data-toc-label="nvidia" }

#SCHEMA# dstack._internal.core.models.backends.aws.AWSOSImage
    overrides:
        show_root_heading: false
        type:
            required: true

##### `projects[n].backends[type=azure]` { #azure data-toc-label="azure" }

#SCHEMA# dstack._internal.server.services.config.AzureConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: azure-

###### `projects[n].backends[type=azure].creds` { #azure-creds data-toc-label="creds" }

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

##### `projects[n].backends[type=gcp]` { #gcp data-toc-label="gcp" }

#SCHEMA# dstack._internal.server.services.config.GCPConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: gcp-

###### `projects[n].backends[type=gcp].creds` { #gcp-creds data-toc-label="creds" }

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

##### `projects[n].backends[type=lambda]` { #lambda data-toc-label="lambda" }

#SCHEMA# dstack._internal.server.services.config.LambdaConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: lambda-

###### `projects[n].backends[type=lambda].creds` { #lambda-creds data-toc-label="creds" }

#SCHEMA# dstack._internal.core.models.backends.lambdalabs.LambdaAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

##### `projects[n].backends[type=runpod]` { #runpod data-toc-label="runpod" }

#SCHEMA# dstack._internal.server.services.config.RunpodConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: runpod-

###### `projects[n].backends[type=runpod].creds` { #runpod-creds data-toc-label="creds" }

#SCHEMA# dstack._internal.core.models.backends.runpod.RunpodAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

##### `projects[n].backends[type=vastai]` { #vastai data-toc-label="vastai" }

#SCHEMA# dstack._internal.server.services.config.VastAIConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: vastai-

###### `projects[n].backends[type=vastai].creds` { #vastai-creds data-toc-label="creds" }

#SCHEMA# dstack._internal.core.models.backends.vastai.VastAIAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

##### `projects[n].backends[type=tensordock]` { #tensordock data-toc-label="tensordock" }

#SCHEMA# dstack._internal.server.services.config.TensorDockConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: tensordock-

###### `projects[n].backends[type=tensordock].creds` { #tensordock-creds data-toc-label="creds" }

#SCHEMA# dstack._internal.core.models.backends.tensordock.TensorDockAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

##### `projects[n].backends[type=oci]` { #oci data-toc-label="oci" }

#SCHEMA# dstack._internal.server.services.config.OCIConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: oci-

###### `projects[n].backends[type=oci].creds` { #oci-creds data-toc-label="creds" }

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

##### `projects[n].backends[type=cudo]` { #cudo data-toc-label="cudo" }

#SCHEMA# dstack._internal.server.services.config.CudoConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: cudo-

###### `projects[n].backends[type=cudo].creds` { #cudo-creds data-toc-label="creds" }

#SCHEMA# dstack._internal.core.models.backends.cudo.CudoAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

##### `projects[n].backends[type=datacrunch]` { #datacrunch data-toc-label="datacrunch" }

#SCHEMA# dstack._internal.server.services.config.DataCrunchConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: datacrunch-

###### `projects[n].backends[type=datacrunch].creds` { #datacrunch-creds data-toc-label="creds" }

#SCHEMA# dstack._internal.core.models.backends.datacrunch.DataCrunchAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

##### `projects[n].backends[type=kubernetes]` { #kubernetes data-toc-label="kubernetes" }

#SCHEMA# dstack._internal.server.services.config.KubernetesConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: kubernetes-

###### `projects[n].backends[type=kubernetes].kubeconfig` { #kubernetes-kubeconfig data-toc-label="kubeconfig" }

##SCHEMA# dstack._internal.server.services.config.KubeconfigConfig
    overrides:
        show_root_heading: false

??? info "Specifying `data`"
    To specify service account file contents as a string, use `jq`:

    ```shell
    cat my-service-account-file.json | jq -c | jq -R
    ```

###### `projects[n].backends[type=kubernetes].networking` { #kubernetes-networking data-toc-label="networking" }

##SCHEMA# dstack._internal.core.models.backends.kubernetes.KubernetesNetworkingConfig
    overrides:
        show_root_heading: false

##### `projects[n].backends[type=vultr]` { #vultr data-toc-label="vultr" }

#SCHEMA# dstack._internal.server.services.config.VultrConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        item_id_prefix: vultr-

###### `projects[n].backends[type=vultr].creds` { #vultr-creds data-toc-label="creds" }

#SCHEMA# dstack._internal.core.models.backends.vultr.VultrAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

### `encryption` { #encryption data-toc-label="encryption" }

#SCHEMA# dstack._internal.server.services.config.EncryptionConfig
    overrides:
        show_root_heading: false

#### `encryption.keys` { #encryption-keys data-toc-label="keys" }

##### `encryption.keys[n][type=identity]` { #encryption-keys-identity data-toc-label="identity" }

#SCHEMA# dstack._internal.server.services.encryption.keys.identity.IdentityEncryptionKeyConfig
    overrides:
        show_root_heading: false
        type:
            required: true

##### `encryption.keys[n][type=aes]` { #encryption-keys-aes data-toc-label="aes" }

#SCHEMA# dstack._internal.server.services.encryption.keys.aes.AESEncryptionKeyConfig
    overrides:
        show_root_heading: false
        type:
            required: true

### `default_permissions` { #default_permissions data-toc-label="default_permissions" }

#SCHEMA# dstack._internal.server.services.permissions.DefaultPermissions
    overrides:
        show_root_heading: false
