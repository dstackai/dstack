# dstack-shim and dstack-runner

For overview of `dstack-shim` and `dstack-runner`, see [/contributing/RUNNER-AND-SHIM.md](../contributing/RUNNER-AND-SHIM.md).

`dstack-shim` and `dstack-runner` can be built only for GOOS=linux. Use containers for development on other OS.

## Testing locally

Run shim and runner tests on any OS inside a Docker container:

```shell
just test-runner-in-container
```

## Running locally (standalone)

Build `dstack-shim` and `dstack-runner` and run them locally:

1. Build the runner executable

    ```shell
    cd runner/cmd/runner
    go build
    ```

2. Build the shim executable

    ```shell
    cd runner/cmd/shim
    go build
    ```

3. Start the shim:

    ```shell
    ./shim --shim-home $RUNNER_DIR --runner-binary-path $COMPILED_RUNNER_PATH
    ```

    Notes:

    * `$RUNNER_DIR` is any directory for storing runner files.

Now you can call shim API:

```shell
>>> from dstack._internal.server.services.runner import client
>>> s = client.ShimClient(port=10998)
>>> s.submit("","", "ubuntu", None)
```

## Running with `dstack`

You can test the built shim and runner with `dstack` using standard backends (including SSH fleets).

> [!NOTE]
> To run with standard backends, both the runner and shim must be built for linux.

Build the runner and shim and upload them to S3 using `just` (see [`justfile`](justfile)).

> [!IMPORTANT]
> Before running any `just` commands that upload to S3, you must set the following environment variables:
>
> ```shell
> export DSTACK_SHIM_UPLOAD_VERSION="your-version"
> export DSTACK_SHIM_UPLOAD_S3_BUCKET="your-bucket"
> ```
>
> These variables are required and must be set before running any upload commands.

```shell
just upload-runner
```

To use the built shim and runner with the `dstack` server, pass the URLs via `DSTACK_SHIM_DOWNLOAD_URL` and `DSTACK_RUNNER_DOWNLOAD_URL`:

```shell
export DSTACK_SHIM_DOWNLOAD_URL="https://${DSTACK_SHIM_UPLOAD_S3_BUCKET}.s3.amazonaws.com/${DSTACK_SHIM_UPLOAD_VERSION}/binaries/dstack-shim-linux-amd64"
export DSTACK_RUNNER_DOWNLOAD_URL="https://${DSTACK_SHIM_UPLOAD_S3_BUCKET}.s3.amazonaws.com/${DSTACK_SHIM_UPLOAD_VERSION}/binaries/dstack-runner-linux-amd64"

dstack server --log-level=debug
```

## Dependencies (WIP)

These are non-exhaustive lists of external dependencies (executables, libraries) of the `dstack-*` binaries.

**TODO**: inspect codebase, add missing dependencies.

### `dstack-shim`

#### Executables

* `mount`
* `umount`
* `mountpoint`
* `lsblk`
* `blkid`
* `mkfs.ext4`
* (NVIDIA GPU SSH fleet instances only) `nvidia-smi`
* (AMD SSH fleet instances only) `docker` (used for `amd-smi` container)
* (Intel Gaudi SSH fleet instances only) `hl-smi`
* ...

Debian/Ubuntu packages: `mount` (`mount`, `umount`), `util-linux` (`mountpoint`, `lsblk`, `blkid`), `e2fsprogs` (`mkfs.ext4`)

### `dstack-runner`

#### Executables

* ...
