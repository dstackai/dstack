# dstack-shim and dstack-runner

For overview of `dstack-shim` and `dstack-runner`, see [/contributing/RUNNER-AND-SHIM.md](../contributing/RUNNER-AND-SHIM.md).

## Running locally

Here's the steps to build `dstack-shim` and `dstack-runner` and run `dstack` with them locally:

1. Build the runner executable

    ```shell
    cd runner/cmd/runner
    go build
    ```

    Note: The runner runs inside the Docker container, so ensure it's compiled for linux/amd64. For example, on macOS you'd run `GOOS=linux GOARCH=amd64 go build`.

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

### Local backend

You can also run `dstack` end-to-end with local shim and runner by enabling the `local` backend on dstack server:

```shell
DSTACK_LOCAL_BACKEND_ENABLED= dstack server --log-level=debug
```

The `local` backend will submit the run to the locally started shim and runner. The CLI will attach to the container just as if it were any other cloud backend:

```shell
✗ dstack apply .                   
 Configuration          .dstack.yml        
 Project                main               
 User                   admin              
 Pool name              default-pool       
 Min resources          2..xCPU, 4GB..     
 Max price              -                  
 Max duration           6h                 
 Spot policy            auto               
 Retry policy           yes                
 Creation policy        reuse-or-create    
 Termination policy     destroy-after-idle 
 Termination idle time  300s               

 #  BACKEND  REGION      INSTANCE         RESOURCES                SPOT  PRICE       
 1  local    local       local            4xCPU, 8GB, 100GB        no    $0          
                                          (disk)                                     
 2  azure    westeurope  Standard_D2s_v3  2xCPU, 8GB, 100GB        yes   $0.012      
                                          (disk)                                     
 3  azure    westeurope  Standard_E2s_v4  2xCPU, 16GB, 100GB       yes   $0.015246   
                                          (disk)                                     
    ...                                                                              
 Shown 3 of 4041 offers, $56.6266 max

Continue? [y/n]:
```

## Testing remotely

You can also test the built shim and runner using standard backends (including SSH fleets).

> [!NOTE]
> To run with standard backends, both the runner and shim must be built for linux/amd64.

Build the runner and shim, and upload them to S3 automatically using `just` (see [`justfile`](justfile)).

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
just upload
```

To use the built shim and runner with the dstack server, pass the URLs via `DSTACK_SHIM_DOWNLOAD_URL` and `DSTACK_RUNNER_DOWNLOAD_URL`:

```shell
export DSTACK_SHIM_DOWNLOAD_URL="https://${DSTACK_SHIM_UPLOAD_S3_BUCKET}.s3.amazonaws.com/${DSTACK_SHIM_UPLOAD_VERSION}/binaries/dstack-shim-linux-amd64"
export DSTACK_RUNNER_DOWNLOAD_URL="https://${DSTACK_SHIM_UPLOAD_S3_BUCKET}.s3.amazonaws.com/${DSTACK_SHIM_UPLOAD_VERSION}/binaries/dstack-runner-linux-amd64"

dstack server --log-level=debug
```

## Dependencies (WIP)

These are nonexhaustive lists of external dependencies (executables, libraries) of the `dstack-*` binaries.

**TODO**: inspect codebase, add missing dependencies.

### `dstack-shim`

#### Executables

* `mount`
* `umount`
* `mountpoint`
* `lsblk`
* `mkfs.ext4`
* (NVIDIA GPU SSH fleet instances only) `nvidia-smi`
* (AMD SSH fleet instances only) `docker` (used for `amd-smi` container)
* (Intel Gaudi SSH fleet instances only) `hl-smi`
* ...

Debian/Ubuntu packages: `mount` (`mount`, `umount`), `util-linux` (`mountpoint`, `lsblk`), `e2fsprogs` (`mkfs.ext4`)

### `dstack-runner`

#### Executables

* ...
