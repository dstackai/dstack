# pip

The easiest way to install `dstack`, is via `pip`:

<div class="termy">

```shell
$ pip install "dstack[aws,gcp,azure,lambda]"
$ dstack start

The server is available at http://127.0.0.1:3000?token=b934d226-e24a-4eab-eb92b353b10f
```

</div>

!!! info "Configure clouds"
    Upon startup, the server sets up the default project called `main`.
    Prior to using `dstack`, make sure to [configure clouds](../guides/clouds.md#configure-backends).