# .dstack.yml (task)

A task can be a batch job or a web app.

The configuration file name must end with `.dstack.yml` (e.g., `.dstack.yml` or `train.dstack.yml` are both acceptable).

## Example

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11" # (Optional) If not specified, your local version is used

commands:
  - pip install -r requirements.txt
  - python train.py
```

</div>

## YAML reference

#SCHEMA# dstack._internal.core.models.configurations.TaskConfiguration
    overrides:
      type:
        required: true
