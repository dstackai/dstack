# dstack pool

## What is `dstack pool`

The primary element that enables you to precisely control how compute instances are used is the `dstack pool`.

- Sometimes the desired instance for the task might not be available. The `dstack pool` will wait for compute instances to become available and, when possible, allocate instances before running tasks on these instances.

- You need reserved compute instances to work on a constant load. The dstack will pre-allocate ondemand instances and allow you to run tasks on them when they are available.

- I want to speed up tasks start. Searching for instances and provisioning the runner will take time. When using dstack pool, tasks will be distributed to already running instances.

- You have your own compute instances. You can connect them to a dstack pool and use them with cloud instances.

## How to use

Any task that runs without setted the argument `--pool` by default uses a pool named `default`.

When you specify a pool name for a task, for example `dstack run --pool mypool` there are two ways the task will be executed:

- if `mypool` exists, the task will be run on a available instance with the suitable configuration
- if `mypool` does not exist, this pool will be created and the compute instances required for the pool are created and connected to that pool.

### CLI

- `dstack pool list`
- `dstack pool create`
- `dstack pool show <poolname>`
- `dstack pool add `
- `dstack pool delete`

### Instance lifecycle

- idle time
- reservation policy (instance termination)
- task retry policy

### Add your own compute instance

When connecting your own instance, it must have public ip-address for the dstack server to connect.

To connect you need to pass the ip-addres and ssh credentials to the command `dstack poll add --host HOST --port PORT --ssh-private-key-fileSSH_PRIVATE_KEY_FILE`.
