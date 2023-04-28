# Cache

!!! info "NOTE:"
    The source code of this example is available in the <a href="https://github.com/dstackai/dstack-playground#readme" target="__blank">Playground</a>.

With `dstack`, you can cache folders for future runs of the same workflow, saving you from downloading the same data or
packages repeatedly.

Define the following workflow:

<div editor-title=".dstack/workflows/cache.yaml"> 

```yaml
workflows:
  - name: hello-cache
    provider: bash
    commands:
      - pip install pandas
      - python usage/python/hello_pandas.py
    cache:
      - path: ~/.cache/pip
```

</div>

Run it locally using `dstack run`:

<div class="termy">

```shell
$ dstack run hello-cache
```

</div>

On the first run, Python packages will be downloaded. On subsequent runs, packages will be installed from the cache.

!!! info "NOTE:"
    The `cache` feature works for both local and remote runs, like any other `dstack` feature.

### Prune cache

To clear the cache for a specific workflow, use the command
[`dstack prune cache`](../reference/cli/prune.md) followed by the workflow name.

<div class="termy">

```shell
$ dstack prune cache zebra-1
```

</div>