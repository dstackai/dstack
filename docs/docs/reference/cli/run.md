# dstack run

This command runs a given configuration.

## Usage

<div class="termy">

```shell
$ dstack run . --help
#GENERATE#
```

</div>

??? info ".gitignore"
    When running dev environments or tasks, `dstack` uses the exact version of code that is present in the folder where you
    use the `dstack run` command.

    If your folder has large files or folders, this may affect the performance of the `dstack run` command. To avoid this,
    make sure to create a `.gitignore` file and include these large files or folders that you don't want to include when
    running dev environments or tasks.

## Arguments reference

### General

- <a href="#WORKING_DIR"><code id="WORKING_DIR">WORKING_DIR</code></a> – (Required) The working directory of the run. Example: `dstack run .`
- <a href="#CONFIGURATION_FILE"><code id="CONFIGURATION_FILE">-f CONFIGURATION_FILE</code></a>, <a href="#CONFIGURATION_FILE"><code>--file CONFIGURATION_FILE</code></a> – (Optional) The configuration file to run.
  If not specified, `dstack` will use the `WORKING_DIR/.dstack.yml` configuration by default.
  Example: `dstack run . -f llama-2/serve.dstack.yml`
- <a href="#RUN_NAME"><code id="RUN_NAME">-n RUN_NAME</code></a>, <a href="#RUN_NAME"><code>--name RUN_NAME</code></a> – (Optional) The name of the run. If not specified, `dstack` will pick a random name.
  Example: `dstack run . -n my-dev-environment`
- <a href="#ENV"><code id="ENV">-e ENV</code></a>, <a href="#ENV"><code>--env ENV</code></a> – (Optional) 
  Set environment variables. Example: `dstack run . -e MYVAR1=foo -e MYVAR2=bar`
- <a href="#PORT"><code id="PORT">-p PORT</code></a>, <a href="#PORT"><code>--port PORT</code></a> – (Optional)
  Configure port forwarding. Examples: `dstack run . -p 8000` (forwards the `8000` port of the task to the same port on
  your local machine) or `dstack run . -p 8001:8000` (forwards the `8000` port of the task to the `8001` port on
  your local machine).
-  <a href="#YES"><code id="YES">-y</code></a>, <a href="#YES"><code>--yes</code></a> - (Optional) Do not ask a confirmation
- <a href="#PROFILE"><code id="PROFILE">-p PROFILE</code></a>, <a href="#PROFILE"><code>--profile PROFILE</code></a> – (Optional) The name of the profile
- <a href="#PROJECT"><code id="PROJECT">-p PROJECT</code></a>, <a href="#PROJECT"><code>--project PROJECT</code></a> – (Optional) The name of the project
- <a href="#DETACH"><code id="DETACH">-d</code></a>, <a href="#DETACH"><code>--detach</code></a> – (Optional) Run in the detached mode (no logs are shown in the output, and the command doesn't wait until the run is finished)

### Compute

- <a href="#GPU"><code id="GPU">--gpu GPU</code></a> – (Optional) Request GPU. Examples:
  `dstack run . --gpu A10` or `dstack run . --gpu 24B` or `dstack run . --gpu A100:8`
- <a href="#MEMORY"><code id="MEMORY">--memory MEMORY</code></a> – (Optional) The minimum size of memory. Examples:
  `dstack run . --memory 64GB`
- <a href="#SHM_SIZE"><code id="SHM_SIZE">--shm_size SHM_SIZE</code></a> – (Optional) The size of shared memory. 
  Required to set if you are using parallel communicating processes.
  Example: `dstack run . --shm_size 8GB`
- <a href="#MAX_PRICE"><code id="MAX_PRICE">--max_price MAX_PRICE</code></a> – (Optional) The maximum price per hour, in dollars.
  Example: `dstack run . --max-price 1.1`
- <a href="#BACKEND"><code id="BACKEND">-backend BACKEND</code></a> – (Optional) 
  Force using listed backends only. Possible values: `aws`, `azure`, `gcp`, `lambda`. 
  If not specified, all configured backends are tried. Example: `dstack run . --backend aws --backend gcp`
- <a href="#SPOT"><code id="SPOT">--spot</code></a> – (Optional) Force using spot instances only.
  Example: `dstack run . --spot`
- <a href="#SPOT_AUTO"><code id="SPOT_AUTO">--spot-auto</code></a> – (Optional) Force using spot instances
  if they are available and on-demand instances otherwise. This is the default for tasks and services.
  Example: `dstack run . --spot-auto`
- <a href="#ON_DEMAND"><code id="ON_DEMAND">--on-demand</code></a> – (Optional) Force using on-demand instances.
  This is the default for dev environments.
  Example: `dstack run . --on-demand`
- <a href="#NO_RETRY"><code id="NO_RETRY">--no-retry</code></a> – (Optional) Do not wait for capacity.
  This is the default.
  Example: `dstack run . --no-retry`
- <a href="#RETRY_LIMIT"><code id="RETRY_LIMIT">--retry-limit RETRY_LIMIT</code></a> – (Optional) The duration
  to wait for capacity.
  Example: `dstack run . --retry-limit 3h` or `dstack run . --retry-limit 2d`
- <a href="#MAX_DURATION"><code id="MAX_DURATION">--max-duration MAX_DURATION</code></a> – (Optional) The maximum duration of a run.
  After it elapses, the run is forced to stop. Protects from running idle instances. Defaults to `6h` for dev environments and to `72h` for tasks.
  Examples: `dstack run . --max-duration 3h` or `dstack run . --max-duration 2d` or `dstack run . --max-duration off`.

### Arguments

- <a href="#ARGS"><code id="ARGS">ARGS</code></a> – (Optional) Pass [custom arguments](../../guides/tasks.md#parametrize-tasks) to the task.

### Experimental

- <a href="#BUILD"><code id="BUILD">--build</code></a> – Pre-build the environment (if you're using the `build` property in [`dstack.yml`](../dstack.yml/index.md)) if it's not pre-built yet.
  Example: `dstack run . --build`
- <a href="#FORCE_BUILD"><code id="FORCE_BUILD">--force-build</code></a> – Force pre-building the environment (if you're using the `build` property in [`dstack.yml`](../dstack.yml/index.md), even if it has been pre-built before.
  Example: `dstack run . --force-build`
- <a href="#RELOAD"><code id="RELOAD">--reload</code></a> – (Optional) Enable auto-reloading of your local changes into the running task.
  Maybe be used together with Streamlit, Fast API, Gradio for auto-reloading local changes.
  Example: `dstack run . --reload`
- <a href="#MAX_OFFERS"><code id="MAX_OFFERS">--max-offers MAX_OFFERS</code></a> – (Optional) Set the maximum number of offers shown
  before the confirmation.

[//]: # (TODO: Add a link to reference/dstack.yml#build)
