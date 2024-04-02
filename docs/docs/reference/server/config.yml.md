# ~/.dstack/server/config.yml

The `~/.dstack/server/config.yml` file is used by the `dstack` server
to [configure](../../installation/index.md#configure-backends) cloud accounts.

!!! info "Projects"
    For flexibility, `dstack` server permits you to configure backends for multiple projects. 
    If you intend to use only one project, name it `main`.

### Examples

#### AWS

=== "Access key"

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

#### Azure

=== "Client"

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

#### GCP

=== "Service account"

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

#### Lambda

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

#### Vast.ai

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

#### CUDO

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

#### DataCrunch

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

=== "Self-managed"
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

=== "Managed"
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

For more details on configuring clouds, please refer to [Installation](../../installation/index.md#configure-backends).

### Root reference

#SCHEMA# dstack._internal.server.services.config.ServerConfig
    overrides:
      show_root_heading: false

### `projects[n]` { #projects data-toc-label="projects" }

#SCHEMA# dstack._internal.server.services.config.ProjectConfig
    overrides:
        show_root_heading: false
        backends:
            type: 'Union[AWSConfigInfoWithCreds, AzureConfigInfoWithCreds, GCPConfigInfoWithCreds, LambdaConfigInfoWithCreds, TensorDockConfigInfoWithCreds, VastAIConfigInfoWithCreds, KubernetesConfig]'

### `projects[n].backends[type=aws]` { #aws data-toc-label="aws" }

#SCHEMA# dstack._internal.server.services.config.AWSConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        reference_prefix: aws-

### `projects[n].backends[type=aws].creds` { #aws-creds data-toc-label="creds" } 

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

### `projects[n].backends[type=azure]` { #azure data-toc-label="azure" }

#SCHEMA# dstack._internal.server.services.config.AzureConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        reference_prefix: azure-

### `projects[n].backends[type=azure].creds` { #azure-creds data-toc-label="creds" } 

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

### `projects[n].backends[type=datacrunch]` { #datacrunch data-toc-label="datacrunch" }

#SCHEMA# dstack._internal.server.services.config.DataCrunchConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        reference_prefix: datacrunch-

### `projects[n].backends[type=datacrunch].creds` { #datacrunch-creds data-toc-label="creds" } 

#SCHEMA# dstack._internal.core.models.backends.datacrunch.DataCrunchAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

### `projects[n].backends[type=gcp]` { #gcp data-toc-label="gcp" }

#SCHEMA# dstack._internal.server.services.config.GCPConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        reference_prefix: gcp-

### `projects[n].backends[type=gcp].creds` { #gcp-creds data-toc-label="creds" } 

=== "Service account"
    #SCHEMA# dstack._internal.server.services.config.GCPServiceAccountCreds
        overrides:
            show_root_heading: false
            type:
                required: true

=== "Default"
    #SCHEMA# dstack._internal.server.services.config.GCPDefaultCreds
        overrides:
            show_root_heading: false
            type:
                required: true

### `projects[n].backends[type=lambda]` { #lambda data-toc-label="lambda" }

#SCHEMA# dstack._internal.server.services.config.LambdaConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        reference_prefix: lambda-

### `projects[n].backends[type=lambda].creds` { #lambda-creds data-toc-label="creds" } 

#SCHEMA# dstack._internal.core.models.backends.lambdalabs.LambdaAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

### `projects[n].backends[type=tensordock]` { #tensordock data-toc-label="tensordock" }

#SCHEMA# dstack._internal.server.services.config.TensorDockConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        reference_prefix: tensordock-

### `projects[n].backends[type=tensordock].creds` { #tensordock-creds data-toc-label="creds" } 

#SCHEMA# dstack._internal.core.models.backends.tensordock.TensorDockAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

### `projects[n].backends[type=vastai]` { #vastai data-toc-label="vastai" }

#SCHEMA# dstack._internal.server.services.config.VastAIConfig
    overrides:
        show_root_heading: false
        type:
            required: true
        reference_prefix: vastai-

### `projects[n].backends[type=vastai].creds` { #vastai-creds data-toc-label="creds" } 

#SCHEMA# dstack._internal.core.models.backends.vastai.VastAIAPIKeyCreds
    overrides:
        show_root_heading: false
        type:
            required: true

### `projects[n].backends[type=kubernetes]` { #kubernetes data-toc-label="kubernetes" }

#SCHEMA# dstack._internal.server.services.config.KubernetesConfig
    overrides:
        show_root_heading: false
        type:
            required: true

### `projects[n].backends[type=kubernetes].kubeconfig` { #kubeconfig data-toc-label="kubeconfig" }

##SCHEMA# dstack._internal.server.services.config.KubeconfigConfig
    overrides:
        show_root_heading: false

### `projects[n].backends[type=kubernetes].networking` { #networking data-toc-label="networking" }

##SCHEMA# dstack._internal.core.models.backends.kubernetes.KubernetesNetworkingConfig
    overrides:
        show_root_heading: false
