# Dev environments

A dev environment is a cloud instance pre-configured with hardware resources, source code, an environment, and
an IDE.

Using `dstack`, you can define such a dev environment through a configuration file and provision it on one of the
configured clouds that offer the best price and availability.

## Define a configuration

To configure a dev environment, create its configuration file. It can be defined
in any folder but must be named with a suffix `.dstack.yml`.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

python: "3.11" # (Optional) If not specified, your local version is used.

setup: # (Optional) Executed once at the first startup.
  - pip install -r requirements.txt

ide: vscode
```

</div>

### Configure the environment

By default, `dstack` uses its own Docker images to run dev environments, which are pre-configured with Python, Conda, and essential CUDA drivers.

You can install packages using `pip` and `conda` executables from `setup`.

??? info "Docker image (experimental)"
    If you prefer to use your custom Docker image, use the `image` property in the configuration.

    However, this requires your image to have `openssh-server` pre-installed. If you want to use a custom Docker
    image with a dev environment and it does not include `openssh-server`, you can install it using the following 
    method:

    <div editor-title=".dstack.yml">

    ```yaml
    type: dev-environment
    
    image: ghcr.io/huggingface/text-generation-inference:0.9
    
    build:
      - apt-get update
      - DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server
      - rm -rf /var/lib/apt/lists/*
 
    ide: vscode
    ```

    </div>

??? info "Build command (experimental)" 

    In case you'd like to pre-build the environment rather than install packaged on every run,
    you can use the `build` property. Here's an example:
    
    <div editor-title=".dstack.yml"> 
    
    ```yaml
    type: dev-environment

    python: "3.11" # (Optional) If not specified, your local version is used.
    
    build:
      - pip install -r requirements.txt --no-cache-dir
    
    ide: vscode
    ```
    
    </div>

    In this case, you have to pass `--build` to `dstack run`.

    <div class="termy">
    
    ```shell
    $ dstack run . --build
    ```
    
    </div>

    If there is no pre-built image, the `dstack run` command will build it and upload it to the storage. If the pre-built
    image is already available, the `dstack run` command will reuse it.

The `.dstack.yml` has many other properties. To view them all, refer to the [Reference](../reference/dstack.yml/dev-environment.md).

## Run the configuration

To run a dev environment, use the `dstack run` command followed by the path to the directory you want to use as the
working directory.

<div class="termy">

```shell
$ dstack run . 

 RUN          CONFIGURATION   BACKEND  RESOURCES        SPOT  PRICE
 fast-moth-1  app.dstack.yml  aws      5xCPUs, 15987MB  yes   $0.0547 
 
Provisioning and starting SSH tunnel...
---> 100%

To open in VS Code Desktop, use this link:
  vscode://vscode-remote/ssh-remote+fast-moth-1/workflow
```

</div>

The `dstack run` command provisions cloud resources, pre-installs the environment, code, and the IDE, and establishes an
SSH tunnel for secure access. 

To open the dev environment via a desktop IDE, click the URL in the output.

![](../../assets/images/dstack-vscode-jupyter.png){ width=800 }

By default, VS Code comes with pre-installed Python and Jupyter extensions.

### Configure resources, price, etc

For every run, you can specify hardware resources like memory and GPU, along with various run policies (e.g., maximum
hourly price, use of spot instances, etc.).

| Example                     | Description                                |
|-----------------------------|--------------------------------------------|
| `dstack run . --gpu A10`    | Use an instance with `NVIDIA A10` GPU      |
| `dstack run . --gpu A100:8` | Use an instance with 8 `NVIDIA A100` GPUs  |
| `dstack run . --gpu 24GB`   | Use an instance with a GPU that has `24GB` |

The `dstack run` command has many options. To view them, refer to the [Reference](../reference/cli/run.md).

??? info "Profiles"
    ### Configure profiles (optional)

    Instead of configuring resources, price, and policies through `dstack run`, you can use profiles. To set up a profile, 
    create the `.dstack/profiles.yml` file in the root folder of the project. 
    
    <div editor-title=".dstack/profiles.yml"> 
    
    ```yaml
    profiles:
      - name: large

        resources:
          memory: 24GB  # (Optional) The minimum amount of RAM memory
          gpu:
            memory: 48GB  # (Optional) The minimum amount of GPU memory 
            
        max_price: 1.5 # (Optional) The maximim price per instance, in dollards.

        max_duration: 1d # (Optional) The maximum duration of the run.

        spot_policy: auto # (Optional) The spot policy. Supports `spot`, `on-demand, and `auto`.

        backends: [azure, lambda]  # (Optional) Use only listed backends 

        default: true # (Optional)
    ```
    
    </div>

    #### Spot instances

    If `spot_policy` is set to `auto`, `dstack` gives priority to spot instances. If unavailable, it uses on-demand instances. 
    To reduce costs, set `spot_policy` to `spot`. Keep in mind that spot instances are much cheaper but may be interrupted. 
    Your code should handle interruptions and resume from saved checkpoints.

    #### Default profile
    
    By default, the `dstack run` command uses the default profile. You 
    can override it by passing the `--profile` argument to the `dstack run` command.
    
    For more details on the syntax of the `profiles.yml` file, refer to the [Reference](../reference/profiles.yml.md).