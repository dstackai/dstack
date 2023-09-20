# Python API

The Python API allows for programmatically running tasks and services across configured clouds.

#### Installation

Before you can use `dstack` Python API, ensure you have installed the `dstack` package, 
started a `dstack` server with [configured clouds](../../docs/docs/guides/clouds.md).
    
```shell
pip install "dstack[all]==0.11.3rc1"
dstack start
```

#### Usage example

The code below runs quantized LLama 2 13B Chat as a task.

<div editor-title=""> 

```python
import sys

import dstack

task = dstack.Task(
    image="ghcr.io/huggingface/text-generation-inference:latest",
    env={"MODEL_ID": "TheBloke/Llama-2-13B-chat-GPTQ"},
    commands=[
        "text-generation-launcher --trust-remote-code --quantize gptq",
    ],
    ports=["8080:80"],
)
resources = dstack.Resources(gpu=dstack.GPU(memory="20GB"))

if __name__ == "__main__":
    print("Initializing the client...")
    client = dstack.Client.from_config(repo_dir="~/dstack-examples")

    print("Submitting the run...")
    run = client.runs.submit(configuration=task, resources=resources)
    
    print(f"Run {run.name}: " + run.status())

    print("Attaching to the run...")
    run.attach()
    
    # After the endpoint is up, http://127.0.0.1:8080/health will return 200 (OK).
    
    try:
        for log in run.logs():
            sys.stdout.buffer.write(log)
            sys.stdout.buffer.flush()
            
    except KeyboardInterrupt:
        print("Aborting the run...")
        run.stop(abort=True)
    finally:
        run.detach()
```

</div>

## Client

To use the `dstack` server, start by creating a client.

### from_config()

Create a new instance of [`dstack.Client`](#client).

The function loads the `dstack` server address and user token from `~/.dstack/config.yml`.

Parameters:

 - `repo_dir: os.PathLike` – (Required) The path to a local directory that acts as a repository.
    When you initiate a run, the client will upload the repository's contents, allowing the run to access any files within.
 - `project_name: Optional[str]` – (Optional) If not specified, it uses the default project.
 - `server_url: Optional[str]` – (Optional) The URL of the `dstack` server. Must be used with `project_name` and `user_token`.
 - `user_token: Optional[str]` – (Optional) The token of the `dstack` user. Must be used with `project_name` and `server_url`.
 - `git_identity_file: Optional[str]` – (Optional) The path to the private SSH key file for non-public Git repositories.
 - `oauth_token: Optional[str]` – (Optional) The authentication token for non-public Git repositories.
 - `ssh_identity_file: Optional[str]` – (Optional) The path to the private SSH key file for SSH port forwarding.
 - `local_repo: bool` – (Optional) If `repo_dir` is a Git repository,
    `dstack` will use it as a Git repository (instead of uploading the entire contents). 
    If you'd like to opt out from this behavior, set `local_repo` to True. It defaults to `False`.
 - `init: bool` – (Optional) By default, `from_config()` is equivalent to [`dstack init`](../../cli/init.md). Set `init`
    to `False` to skip automatic repo initialization.

### runs

This property returns an instance of [`dstack.RunCollection`](#runcollection).

## Runs

Methods available on [`client.runs`](#runs):

### submit()

Submit a new run.

Parameters:

- `configuration: Union[Task, Service]` – (Required) The configuration of the run. Can be either [`dstack.Task`](#task) or [`dstack.Service`](#service).
- `run_name: Optional[str]` – (Optional) The name of the run. Defaults to a randon name.
- `resources: Optional[Resources]` – (Optional) The hardware resources required by the run.
- `spot_policy: Optional[SpotPolicy]` – (Optional) The policy of using spot instances. See [`dstack.SpotPolicy`](#spotpolicy).
- `retry_policy: Optiona[RetryPolicy]` – (Optional) The policy of waiting for capacity. See [`dstack.RetryPolicy`](#retrypolicy).
- `max_duration: Optional[Union[int, str]]` – (Optional) The maximum duration of the run.
- `max_price: Optional[float]` – (Optional) The maximum price for computing per hour in dollars.
- `working_dir: Optional[str]` – (Optional) Defaults to the root of the repo dir (see [`dstack.Client.from_config`](#fromconfig)).
- `verify_ports: bool` – (Optional) Verify port availability before submitting the run. Defaults to `True`. 

!!! info "NOTE:"
    The call of `RunCollection.submit()` is equal to [`dstack run`](../../cli/run.md).

[//]: # (TODO: backends)

### list()

Load the list of runs within the current repo.

Parameters:

- `all: bool` – (Optional) Load all runs. If not set to `True`, returns only unfinished or the latest finished runs.

### get()

Load a run by name.

Parameters:

- `run_name: str` - (Required) The name of the run.

## Task

A configuration of a [task](../../../guides/tasks.md).

Parameters:

- `commands: Optional[str]` – (Optional) The list of shell commands to run. 
- `ports: Optional[List[Union[int,str,PortMapping]]]` – (Optional) List of ports or mapping rules. When you run `run.attach()`,
  configured ports will be forwarded to your local machine based on the rules. For instance, `"8080:8000"` maps
  port `8000` to local port `8080`.
- `env: Optional[Union[List[str], Dict[str,str]]]` - (Optional) The environment variables.
- `python: Optional[str]` – (Optional) The major version of Python. Mutually exclusive to `image`.
- `image: Optional[str]` – (Optional) The Docker image. Mutually exclusive to `python`.
- `entrypoint: Optional[]` - (Optional) Override the entrypoint of the Docker image. 
- `registry_auth: Optional[RegistryAuth]` – (Optional) The credentials to access the private Docker registry.

## Service

A configuration of a [service](../../../guides/services.md).

Parameters:

- `commands: Optional[str]` – (Optional) The list of shell commands to run. 
- `port: Optional[Union[int,str]]` – (Required) The port of the service.
- `env: Optional[Union[List[str], Dict[str,str]]]` - (Optional) The environment variables.
- `python: Optional[str]` – (Optional) The major version of Python. Mutually exclusive to `image`.
- `image: Optional[str]` – (Optional) The Docker image. Mutually exclusive to `python`.
- `entrypoint: Optional[]` - (Optional) Override the entrypoint of the Docker image. 
- `registry_auth: Optional[RegistryAuth]` – (Optional) The credentials to access the private Docker registry.

## Run

### name

Returns the name of the run. Unique within a project.

### status()

Returns the current status of the run. See [`dstack.RunStatus`](#runstatus).

### attach()

Wait until the run status changes from `dstack.RunStatus.SUBMITTED` or `dstack.RunStatus.PENDING`, and establish an SSH
tunnel to the run container for streaming logs and port forwarding.

### detach()

Close the SSH tunnel.

### stop()

Stop the run.

Parameters:

- `abort: bool` – (Optional) If `True`, do not wait for a graceful stop. Defaults to `False`.

## Resources

Parameters:

- `gpu: Optional[GPU]` – (Optional) The minimum GPU requirements. See [`dstack.GPU`](#gpu).
- `memory: Optional[Union[int, str]]` – (Optional) The minimum RAM requirements, `"24GB"`.
- `shm_size: Optional[Union[int, str]]` – (Optional) The size of shared memory, `"12GB"`.

## GPU

The minimum GPU requirements.

Attributes:

- `name: Optional[str]` – (Optional) The name of the GPU, e.g. `"A100"`.
- `count: Optional[int]` – (Optional) The number of GPU.
- `memory: Optional[Union[int, str]]` – (Optional) The minimum VRAM requirements, e.g. `"24GB"`.

## RetryPolicy

The policy of waiting for capacity.

Attributes:

- `retry: Optional[str]` – (Optional) Defaults to `False`.
- `limit: Optional[Union[int, str]]` – (Optional) The maximum duration of retrying, e.g. `3d` or `12h`.

## SpotPolicy

The policy of using spot instances.

Possible values:

- `SpotPolicy.AUTO` – Use spot instances when available; otherwise, use on-demand instances. 
- `SpotPolicy.SPOT` – Use spot instances only. 
- `SpotPolicy.ON_DEMAN` – Use on-demand instances only. 

## RegistryAuth

The credentials to access the private Docker registry.

Attributes:

- `username: str` – (Required) The username.
- `password: str` – (Required) The password or secure token.

## RunStatus

The status of the run.

Possible values: `PENDING`, `SUBMITTED`, `DOWNLOADING`, `BUILDING`, `RUNNING`, `UPLOADING`, `STOPPING`, `STOPPED`, 
`RESTARTING`, `TERMINATING`, `TERMINATED`, `ABORTING`, `ABORTED`, `FAILED`, `DONE`.
