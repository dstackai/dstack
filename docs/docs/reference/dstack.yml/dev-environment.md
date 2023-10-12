# .dstack.yml (dev-environment)

A dev environment is a cloud instance pre-configured with an IDE.

The configuration file name must end with `.dstack.yml` (e.g., `.dstack.yml` or `dev.dstack.yml` are both acceptable).

## Example

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

python: "3.11" # (Optional) If not specified, your local version is used

ide: vscode
```

</div>

## YAML reference

#SCHEMA# dstack._internal.core.models.configurations.DevEnvironmentConfiguration
    overrides:
      type:
        required: true
