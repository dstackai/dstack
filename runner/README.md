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
    ./shim --home $RUNNER_DIR --runner-binary-path $COMPILED_RUNNER_PATH docker --ssh-key $DSTACK_PUBLIC_KEY
    ```

    Notes:

    * `$RUNNER_DIR` is any directory for storing runner files.
    * `$DSTACK_PUBLIC_KEY` is `~/.dstack/ssh/id_rsa.pub` that allows the dstack CLI to connect to the ssh server inside the container.

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
✗ dstack run .                   
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