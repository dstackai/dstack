# `volume`

The `volume` configuration type allows creating, registering, and updating [volumes](../../concepts/volumes.md).

=== "AWS"

    #SCHEMA# dstack._internal.core.models.volumes.AWSVolumeConfiguration
        overrides:
            show_root_heading: false
            backend:
                required: true

=== "GCP"

    #SCHEMA# dstack._internal.core.models.volumes.GCPVolumeConfiguration
        overrides:
            show_root_heading: false
            backend:
                required: true

=== "Runpod"

    #SCHEMA# dstack._internal.core.models.volumes.RunpodVolumeConfiguration
        overrides:
            show_root_heading: false
            backend:
                required: true

=== "Kubernetes"

    Kubernetes backend volumes are mapped to [`PersistentVolumeClaim`](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#persistentvolumeclaims) objects.

    Set `region` to an enabled kubeconfig context name from the
    [backend configuration](../../concepts/backends.md#kubernetes), even if only one context is enabled.
    The claim is created or looked up in that context's namespace.
    You can omit `region` only with the legacy backend configuration without `contexts`, which
    uses the kubeconfig's `current-context` and the backend's `namespace` setting.

    To create a new claim, specify `size` and optionally `storage_class_name` and/or `access_modes`:

    ```yaml
    type: volume
    backend: kubernetes
    region: gpu-cluster-a
    name: new-volume
    size: 100GB
    # By default, storage_class_name is not set, and the decision is delegated to
    # the DefaultStorageClass admission controller (if it is enabled)
    storage_class_name: test-nfs
    # access_modes defaults to [ReadWriteOnce]. For multi-attach-capable volumes
    # use ReadWriteMany and/or ReadOnlyMany
    access_modes:
      - ReadWriteMany
    ```

    To reuse an existing claim, specify `claim_name`:

    ```yaml
    type: volume
    backend: kubernetes
    region: gpu-cluster-a
    name: existing-volume
    claim_name: existing-pvc
    ```

    #SCHEMA# dstack._internal.core.models.volumes.KubernetesVolumeConfiguration
        overrides:
            show_root_heading: false
            backend:
                required: true
            region:
                required: true
