# Environment variables

!!! info "NOTE:"
    The source code of this example is available in the [Playground](../playground.md).

The workflow below sets environment variables:

<div editor-title=".dstack/workflows/envs.yaml"> 

```yaml hl_lines="5 6 7"
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

</div>
