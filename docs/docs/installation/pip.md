# pip

The easiest way to install `dstack`, is via `pip`:

<div class="termy">

```shell
$ pip install "dstack[aws,gcp,azure,lambda]"
$ dstack start

The server is available at http://127.0.0.1:3000?token=b934d226-e24a-4eab-eb92b353b10f
```

</div>

On startup, the server sets up a default project that runs everything locally.

!!! info "Projects"
    To run dev environments and tasks in your cloud, log into the UI, create the corresponding project, 
    and [configure](../guides/projects.md) the CLI to use it.