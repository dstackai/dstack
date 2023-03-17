# Args

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

If you pass any arguments to the `dstack run` command, they can be accessed from the workflow YAML file via
the `${{ run.args }}` expression. 

Create the following Python script:

<div editor-title="args/hello-arg.py">

```python
import sys

if __name__ == '__main__':
    print(sys.argv)
```

</div> 

Then, define the following workflow YAML file:

<div editor-title=".dstack/workflows/args.yaml"> 

```yaml
workflows:
  - name: hello-args
    provider: bash
    commands:
      - python args/hello-arg.py ${{ run.args }}
```
 
</div>

Run it locally using `dstack run` and passing `"Hello, world!"` as an argument:

<div class="termy">

```shell
$ dstack run hello-arg "Hello, world!"
```

</div>

!!! info "NOTE:"
    It supports any arguments except those that are reserved for the [`dstack run`](../reference/cli/run.md) command.