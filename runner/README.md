# dstack-shim and dstack-runner

For overview of `dstack-shim` and `dstack-runner`, see [/contributing/RUNNER-AND-SHIM.md](../contributing/RUNNER-AND-SHIM.md).

## Development

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
