# Self-hosted runners

A runner is a machine that can run `dstack` workflows. You can host runners on your local machine or
on your remote machines.

In order to host a runner on any machine, you have to launch the `dstack-runner` daemon there. 
The machines that host the `dstack-runner` daemon form a pool of runners, and when the user runs workflows via the 
`dstack` CLI, the workflows will be running on these machines.

!!! success ""
    If you don't want to use remote machines, you can host a runner locally.
    All you need to do is to launch the `dstack-runner` daemon locally.

## Install the daemon

!!! warning "Linux"
    Currently, self-hosted runners work on `Linux` only. The `Windows` and `macOS` support is experimental. 
    If you'd like to try it, please write to [hello@dstack.ai](mailto:hello@dstack.ai).

Here's how to install the `dstack-runner` daemon:

```bash
curl -fsSL https://get.dstack.ai/runner -o get-dstack-runner.sh
sudo sh get-dstack-runner.sh
```
    
## Configure a token

Before you can start the daemon, you have to configure it with your `Personal Access Token`:

[//]: # (=== "Linux")

```bash
dstack-runner config --token <token>
```

The provided `Personal Access Token` will be stored in the `~/.dstack/config.yaml` file. 

!!! info "Personal Access Token"
    In order to receive your `Personal Access Token`, please click `Request access` at [dstack.ai](https://dstack.ai). 
    Once your request is approved, you'll be able to create a `dstack` user, and obtain your token.

Once you do it, the daemon is ready to start:

```bash
dstack-runner start
```

[//]: # (=== "macOS")

[//]: # ()
[//]: # (    ```bash)

[//]: # (    dstack-runner start)

[//]: # (    ```)

[//]: # ()
[//]: # (=== "Windows")

[//]: # ()
[//]: # (    ```cmd)

[//]: # (    dstack-runner.exe start)

[//]: # (    ```)

!!! warning "Docker is required"
    The `dstack-runner` daemon requires that either the standard Docker or the NVIDIA's Docker is installed and 
    running on the machine.

!!! warning "Internet is required"
    The machine where you run the `dstack-runner` daemon has to have a connection to the Internet. 

    If your machine is an EC2 instance, make sure its security group allows outgoing traffic. 

## List runners

After you've set up runners, you can check their status via the `dstack` CLI:

```bash
dstack runners 
```

If runners are running properly, you'll see their hosts in the output:

```bash
RUNNER    HOST                    STATUS    UPDATED
sugar-1   MBP-de-Boris.fritz.box  LIVE      3 mins ago
```

!!! bug "Runner is not there?"
    Don't see your runner? This may mean the runner is offline or that the `dstack-runner` daemon
    was not configured or started properly.