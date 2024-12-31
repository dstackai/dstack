# ~/.dstack/server/config.yml

The `~/.dstack/server/config.yml` file is used
to [configure](../../installation/index.md#1-configure-backends) the `dstack` server cloud accounts
and other sever-level settings such as encryption.

## Root reference

#SCHEMA# dstack._internal.server.services.config.ServerConfig
    overrides:
      show_root_heading: false

### `projects[n]` { #projects data-toc-label="projects" }

#SCHEMA# dstack._internal.server.services.config.ProjectConfig
    overrides:
        show_root_heading: false
        backends:
            type: 'Union[AWSConfigInfoWithCreds, AzureConfigInfoWithCreds, GCPConfigInfoWithCreds, LambdaConfigInfoWithCreds, TensorDockConfigInfoWithCreds, VastAIConfigInfoWithCreds, KubernetesConfig]'

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

###### `projects[n].backends[type=runpod]` { #runpod data-toc-label="runpod" }

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

###### `projects[n].backends[type=vastai]` { #vastai data-toc-label="vastai" }

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

###### `projects[n].backends[type=kubernetes].networking` { #kuberentes-networking data-toc-label="networking" }

##SCHEMA# dstack._internal.core.models.backends.kubernetes.KubernetesNetworkingConfig
    overrides:
        show_root_heading: false

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

## Examples

> The `dstack` server allows you to configure backends for multiple projects.
> If you don't need multiple projects, use only the `main` project.

### Encryption keys { #examples-encryption }

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