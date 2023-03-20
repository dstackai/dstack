# Private Docker Registry

To pass registry credentials to the runner you can use `registry_auth.username`
and `registry_auth.password`. These fields will be securely interpolated
from secrets by the runner.

<div editor-title=".dstack/workflows/private-registry.yaml">

```yaml
workflows:
  - name: private-registry
    provider: docker
    image: ghcr.io/my-organization/top-secret-image:v1
    registry_auth:
      username: $GHCR_USER
      password: $GHCR_TOKEN
```

</div>

!!! info "NOTE:"
    `GHCR_USER` and `GHCR_TOKEN` should be previously added to [secrets](secrets.md).

## Interpolation syntax

* `$VAR_NAME` — substitute `VAR_NAME` secret
* `${VAR_NAME}` — substitute `VAR_NAME` secret
* `$$` — escaped single `$`

If a secret doesn't exist, an empty string will be substituted.
