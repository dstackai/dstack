# Environment variables

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

The workflow below sets environment variables:

<div editor-title=".dstack/workflows/envs.yaml"> 

```yaml
workflows:
  - name: hello-env
    provider: bash
    env:
      - DSTACK_ENV_1=VAL1
      - DSTACK_ENV_2=VAL2
      - DSTACK_ENV_3
    commands:
      - env
```

</div