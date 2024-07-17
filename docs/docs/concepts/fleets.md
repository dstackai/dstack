# Fleets

Fleets enable efficient provisioning and management of clusters and instances.
Using fleets, you can launch multiple cloud VMs or add an on-prem cluster in one command,
reserve compute capacity, specify connectivity requirements,
and choose optimal instances for your workloads.

## Creating fleets

You can create and update fleets manually by defining `fleet` configurations.
If explicit fleet management is not required, `dstack run` can create and delete fleets transparently for you.

### Cloud fleets

To provision a cloud fleet, first create a YAML file in your project folder.
Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are both acceptable).

<div editor-title="my-gcp-fleet.dstack.yml"> 

```yaml
type: fleet
name: my-gcp-fleet
nodes: 4
placement: cluster
backends: [gcp]
resources:
  gpu: 1
```

</div>

Then apply the configuration by running `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f .dstack/confs/fleet.yaml
Fleet my-gcp-fleet does not exist yet. Create the fleet? [y/n]: y
 FLEET         INSTANCE  BACKEND  RESOURCES  PRICE  STATUS   CREATED 
 my-gcp-fleet  0                                    pending  now     
               1                                    pending  now     
               2                                    pending  now     
               3                                    pending  now     
```

</div>

Soon `dstack` will provision all instances in the fleet:

<div class="termy">

```shell
dstack fleet
 FLEET         INSTANCE  BACKEND       RESOURCES     PRICE    STATUS  CREATED    
 my-gcp-fleet  0         gcp           2xCPU, 13GB,  $0.1051  idle    3 mins ago 
                         (europe-wes…  1xT4 (16GB),                              
                                       100.0GB                                   
                                       (disk), SPOT                              
               1         gcp           2xCPU, 13GB,  $0.1051  idle    3 mins ago 
                         (europe-wes…  1xT4 (16GB),                              
                                       100.0GB                                   
                                       (disk), SPOT                              
               2         gcp           2xCPU, 13GB,  $0.1051  idle    3 mins ago 
                         (europe-wes…  1xT4 (16GB),                              
                                       100.0GB                                   
                                       (disk), SPOT                              
               3         gcp           2xCPU, 13GB,  $0.1051  idle    3 mins ago 
                         (europe-wes…  1xT4 (16GB),                              
                                       100.0GB                                   
                                       (disk), SPOT 
```

</div>

Once instances become `idle`, they can be used by `dstack run`.

The `fleet` configuration allows specifying resource requirements, along with the spot policy, idle duration, max
price, retry policy, and other policies.
You can also specify the policies via [`.dstack/profiles.yml`](../reference/profiles.yml.md) instead of passing them as arguments. 
For more details on policies and their defaults, refer to [`.dstack/profiles.yml`](../reference/profiles.yml.md).

??? info "Limitations"
    Provisioning fleets is not supported for `kubernetes`, `vastai`, and `runpod` backends yet.

### On-prem fleets

To add an on-prem fleet, first create a YAML file in your project folder.
Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are both acceptable).

<div editor-title="my-ssh-fleet.dstack.yml"> 

```yaml
type: fleet
name: my-ssh-fleet
ssh:
  user: ubuntu
  ssh_key_path: ~/.ssh/key.pem
  hosts:
    - "3.255.177.51"
    - "3.255.177.52"
```

</div>

Then apply the configuration by running `dstack apply`:

<div class="termy">

```shell
✗ dstack apply -f .dstack/confs/fleet-ssh.yaml 
Fleet my-ssh-fleet does not exist yet. Create the fleet? [y/n]: y
 FLEET         INSTANCE  BACKEND       RESOURCES  PRICE  STATUS   CREATED 
 my-ssh-fleet  0         ssh (remote)             $0.0   pending  now     
               1         ssh (remote)             $0.0   pending  now  
  
```

</div>

Soon `dstack` will set up all instances in the fleet:

<div class="termy">

```shell
✗ dstack fleet                                 
 FLEET         INSTANCE  BACKEND       RESOURCES                         PRICE  STATUS  CREATED   
 my-ssh-fleet  0         ssh (remote)  4xCPU, 15GB, 16.8GB (disk), SPOT  $0.0   idle    1 min ago 
               1         ssh (remote)  4xCPU, 15GB, 16.8GB (disk), SPOT  $0.0   idle    1 min ago 
```

</div>

Once instances become `idle`, they can be used by `dstack run`.

!!! warning "Requirements"
    The on-prem instances should be pre-installed with CUDA 12.1 and NVIDIA Docker.

??? info "On-prem clusters"
    If you want on-prem instances to run multi-node tasks, ensure these on-prem servers share the same private network.
    Specify the `network` parameter in the `fleet` configuration.

### Automatic fleets

By default the `dstack run` command tries to reuse idle instances from existing fleets.
If no idle instances meet the requirements, `dstack run` creates a fleet and provisions new instances.

??? info "Reuse policy"
    To avoid provisioning new cloud instances with `dstack run`, specify `--reuse`.
    The run will be forced to use idle instance and fail if there are no idle instances matching the requirements.

??? info "Idle duration"
    By default, `dstack run` sets the idle duration of a newly provisioned instance to `5m`.
    This means that if the run is finished and the instance remains idle for longer than five minutes,
    the instance is automatically deleted. To override the default idle duration, use  `--idle-duration DURATION` with `dstack run`.

## Deleting fleets and instances

If the instance remains idle for the configured idle duration, `dstack` removes it and deletes all cloud resources.
Fleets created by `dstack run` are automatically deleted when all fleet instances terminate.

Fleets created with `dstack apply` can be deleted by passing the `fleet` configuration to `dstack delete`.

<div class="termy">

```shell
$ dstack delete -f .dstack/confs/fleet.yaml
Delete the fleet my-gcp-fleet? [y/n]: y
Fleet my-gcp-fleet deleted
```

</div>

Any fleet can also be deleted with `dstack fleet rm` command:

<div class="termy">

```shell
$ dstack fleet rm my-gcp-fleet
Delete the fleet my-gcp-fleet? [y/n]: 
Fleet my-gcp-fleet deleted
```

</div>

Deleting a fleet will terminate all instances in the fleet.
To terminate and delete only specific instances from the fleet, pass `-i INSTANCE_NUM` to `dstack fleet rm`:

To remove an instance from the pool manually, use the `dstack pool rm` command. 

<div class="termy">

```shell
$ dstack fleet rm my-gcp-fleet -i 3       
Delete the fleet my-gcp-fleet instances [3]? [y/n]: y
Fleet my-gcp-fleet instances deleted
```

</div>
