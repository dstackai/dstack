# Migrate from Slurm

Both Slurm and `dstack` are open-source workload orchestration systems designed to manage compute resources and schedule jobs. This guide compares Slurm and `dstack`, maps features between the two systems, and shows their `dstack` equivalents.

!!! tip "Slurm vs dstack"
    Slurm is a battle-tested system with decades of production use in HPC environments. `dstack` is designed for modern ML/AI workloads with cloud-native provisioning and container-first architecture. Slurm is better suited for traditional HPC centers with static clusters; `dstack` is better suited for cloud-native ML teams working with cloud GPUs. Both systems can handle distributed training and batch workloads—the choice depends on your preferences. 

| | Slurm | dstack |
|---|-------|--------|
| **Provisioning** | Pre-configured static clusters; cloud requires third-party integrations with potential limitations | Native integration with top GPU clouds; automatically provisions clusters on demand |
| **Containers** | Optional via plugins | Built around containers from the ground up |
| **Use cases** | Batch job scheduling and distributed training | Interactive development, distributed training, and production inference services |
| **Personas** | HPC centers, academic institutions, research labs | ML engineering teams, AI startups, cloud-native organizations |

While `dstack` is use-case agnostic and natively supports development and production-grade inference, this guide focuses only on training workloads.

## Architecture

Both Slurm and `dstack` follow a client-server architecture with a control plane and a compute plane running on cluster instances.

| | Slurm | dstack |
|---|---------------|-------------------|
| **Control plane** | `slurmctld` (controller) | `dstack-server` |
| **State persistence** | `slurmdbd` (database) | `dstack-server` (SQLite/PostgreSQL) |
| **REST API** | `slurmrestd` (REST API) | `dstack-server` (HTTP API) |
| **Compute plane** | `slurmd` (compute agent) | `dstack-shim` (on VMs/hosts) and/or `dstack-runner` (inside containers) |
| **Client** | CLI from login nodes | CLI from anywhere |
| **High availability** | Active-passive failover (typically 2 controller nodes) | Horizontal scaling with multiple server replicas (requires PostgreSQL) |

## Job configuration and submission

Both Slurm and `dstack` allow defining jobs as files and submitting them via CLI.

### Slurm

Slurm uses shell scripts with `#SBATCH` directives embedded in the script:

<div editor-title="train.sh">

```bash
#!/bin/bash
#SBATCH --job-name=train-model
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=2:00:00
#SBATCH --partition=gpu
#SBATCH --output=train-%j.out
#SBATCH --error=train-%j.err

export HF_TOKEN
export LEARNING_RATE=0.001

module load python/3.9
srun python train.py --batch-size=64
```

</div>

Submit the job from a login node (with environment variables that override script defaults):

<div class="termy">

```shell
$ sbatch --export=ALL,LEARNING_RATE=0.002 train.sh
  Submitted batch job 12346
```

</div>

### dstack

`dstack` uses declarative YAML configuration files:

<div editor-title=".dstack.yml">

```yaml
type: task
name: train-model

python: 3.9
repos:
  - .

env:
  - HF_TOKEN
  - LEARNING_RATE=0.001

commands:
  - python train.py --batch-size=64

resources:
  gpu: 1
  memory: 32GB
  cpu: 8
  shm_size: 8GB

max_duration: 2h
```

</div>

Submit the job from anywhere (laptop, CI/CD) via the CLI. `dstack apply` allows overriding various options and runs in attached mode by default, streaming job output in real-time:

<div class="termy">

```shell
$ dstack apply -f .dstack.yml --env LEARNING_RATE=0.002

 #  BACKEND  REGION    RESOURCES          SPOT  PRICE
 1  aws      us-east-1  4xCPU, 16GB, T4:1  yes   $0.10

Submit the run train-model? [y/n]: y

Launching `train-model`...
---> 100%
```

</div>

### Configuration comparison

| | Slurm | dstack |
|---|-------|--------|
| **File type** | Shell script with `#SBATCH` directives | YAML configuration file (`.dstack.yml`) |
| **GPU** | `--gres=gpu:N` or `--gres=gpu:type:N` | `gpu: A100:80GB:4` or `gpu: 40GB..80GB:2..8` (supports ranges) |
| **Memory** | `--mem=M` (per node) or `--mem-per-cpu=M` | `memory: 200GB..` (range, per node, minimum requirement) |
| **CPU** | `--cpus-per-task=C` or `--ntasks` | `cpu: 32` (per node) |
| **Shared memory** | Configured on host | `shm_size: 24GB` (explicit) |
| **Duration** | `--time=2:00:00` | `max_duration: 2h` (both enforce walltime) |
| **Cluster** | `--partition=gpu` | `fleets: [gpu]` (see Partitions and fleets below) |
| **Output** | `--output=train-%j.out` (writes files) | `dstack logs` or UI (streams via API) |
| **Working directory** | `--chdir=/path/to/dir` or defaults to submission directory | `working_dir: /path/to/dir` (defaults to image's working directory, typically `/dstack/run`) |
| **Environment variables** | `export VAR` or `--export=ALL,VAR=value` | `env: - VAR` or `--env VAR=value` |
| **Node exclusivity** | `--exclusive` (entire node) | Automatic if `blocks` is not used or job uses all blocks; required for distributed tasks (`nodes` > 1) |

> For multi-node examples, see [Distributed training](#distributed-training) below.

## Containers

### Slurm

By default, Slurm runs jobs on compute nodes using the host OS with cgroups for resource isolation and full access to the host filesystem. Container execution is optional via plugins but require explicit filesystem mounts.

=== "Singularity/Apptainer"

    Container image must exist on shared filesystem. Mount host directories with `--container-mounts`:

    ```bash
    #!/bin/bash
    #SBATCH --nodes=1
    #SBATCH --gres=gpu:1
    #SBATCH --mem=32G
    #SBATCH --time=2:00:00

    srun --container-image=/shared/images/pytorch-2.0-cuda11.8.sif \
      --container-mounts=/shared/datasets:/datasets,/shared/checkpoints:/checkpoints \
      python train.py --batch-size=64
    ```

=== "Pyxis with Enroot"

    Pyxis plugin pulls images from Docker registry. Mount host directories with `--container-mounts`:

    ```bash
    #!/bin/bash
    #SBATCH --nodes=1
    #SBATCH --gres=gpu:1
    #SBATCH --mem=32G
    #SBATCH --time=2:00:00

    srun --container-image=pytorch/pytorch:2.0.0-cuda11.8-cudnn8-runtime \
      --container-mounts=/shared/datasets:/datasets,/shared/checkpoints:/checkpoints \
      python train.py --batch-size=64
    ```

=== "Enroot"

    Pulls images from registry. Mount host directories with `--container-mounts`:

    ```bash
    #!/bin/bash
    #SBATCH --nodes=1
    #SBATCH --gres=gpu:1
    #SBATCH --mem=32G
    #SBATCH --time=2:00:00

    srun --container-image=docker://pytorch/pytorch:2.0.0-cuda11.8-cudnn8-runtime \
      --container-mounts=/shared/datasets:/datasets,/shared/checkpoints:/checkpoints \
      python train.py --batch-size=64
    ```

### dstack

`dstack` always uses container. If `image` is not specified, `dstack` uses a base Docker image with `uv`, `python`, essential CUDA drivers, and other dependencies. You can also specify your own Docker image:

=== "Public registry"

    ```yaml
    type: task
    name: train-with-image

    image: pytorch/pytorch:2.0.0-cuda11.8-cudnn8-runtime

    repos:
      - .

    commands:
      - python train.py --batch-size=64

    resources:
      gpu: 1
      memory: 32GB
    ```

=== "Private registry"

    ```yaml
    type: task
    name: train-ngc

    image: nvcr.io/nvidia/pytorch:24.01-py3

    registry_auth:
      username: $oauthtoken
      password: ${{ secrets.nvidia_ngc_api_key }}

    repos:
      - .

    commands:
      - python train.py --batch-size=64

    resources:
      gpu: 1
      memory: 32GB
    ```

`dstack` can automatically upload files via `repos` or `files`, or mount filesystems via `volumes`. See [Filesystems and data access](#filesystems-and-data-access) below.

## Distributed training

Both Slurm and `dstack` schedule distributed workloads over clusters with fast interconnect, automatically propagating environment variables required by distributed frameworks (PyTorch DDP, DeepSpeed, FSDP, etc.).

### Slurm

Slurm explicitly controls both `nodes` and processes/tasks.

=== "PyTorch DDP"

    ```bash
    #!/bin/bash
    #SBATCH --job-name=distributed-train
    #SBATCH --nodes=4
    #SBATCH --ntasks-per-node=1  # One task per node
    #SBATCH --gres=gpu:8         # 8 GPUs per node
    #SBATCH --mem=200G
    #SBATCH --time=24:00:00
    #SBATCH --partition=gpu

    # Set up distributed training environment
    MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n 1)
    MASTER_PORT=12345

    export MASTER_ADDR MASTER_PORT

    # Launch training with torchrun (torch.distributed.launch is deprecated)
    srun torchrun \
    --nnodes="$SLURM_JOB_NUM_NODES" \
    --nproc_per_node=8 \
    --node_rank="$SLURM_NODEID" \
    --rdzv_backend=c10d \
    --rdzv_endpoint="$MASTER_ADDR:$MASTER_PORT" \
    train.py \
    --model llama-7b \
    --batch-size=32 \
    --epochs=10
    ```


=== "MPI"

    ```bash
    #!/bin/bash
    #SBATCH --nodes=2
    #SBATCH --ntasks=16
    #SBATCH --gres=gpu:8
    #SBATCH --mem=200G
    #SBATCH --time=24:00:00

    export MASTER_ADDR=$(scontrol show hostnames $SLURM_NODELIST | head -n1)
    export MASTER_PORT=12345

    # Convert SLURM_JOB_NODELIST to hostfile format
    HOSTFILE=$(mktemp)
    scontrol show hostnames $SLURM_JOB_NODELIST | awk -v slots=$SLURM_NTASKS_PER_NODE '{print $0" slots="slots}' > $HOSTFILE

    # MPI with NCCL tests or custom MPI application
    mpirun \
    --allow-run-as-root \
    --hostfile $HOSTFILE \
    -n $SLURM_NTASKS \
    --bind-to none \
    /opt/nccl-tests/build/all_reduce_perf -b 8 -e 8G -f 2 -g 1

    rm -f $HOSTFILE
    ```

### dstack

`dstack` only specifies `nodes`. A run with multiple nodes creates multiple jobs (one per node), each running in a container on a particular instance. Inside the job container, processes are determined by the user's `commands`.

=== "PyTorch DDP"

    ```yaml
    type: task
    name: distributed-train-pytorch

    nodes: 4

    python: 3.12
    repos:
    - .

    env:
    - NCCL_DEBUG=INFO
    - NCCL_IB_DISABLE=0
    - NCCL_SOCKET_IFNAME=eth0

    commands:
    - |
        torchrun \
        --nproc-per-node=$DSTACK_GPUS_PER_NODE \
        --node-rank=$DSTACK_NODE_RANK \
        --nnodes=$DSTACK_NODES_NUM \
        --master-addr=$DSTACK_MASTER_NODE_IP \
        --master-port=12345 \
        train.py \
        --model llama-7b \
        --batch-size=32 \
        --epochs=10

    resources:
    gpu: A100:80GB:8
    memory: 200GB..
    shm_size: 24GB

    max_duration: 24h
    ```

=== "MPI"

    For MPI workloads that require specific job startup and termination behavior, `dstack` provides `startup_order` and `stop_criteria` properties. The master node (rank 0) runs the MPI command, while worker nodes wait for the master to complete.

    ```yaml
    type: task
    name: nccl-tests

    nodes: 2
    startup_order: workers-first
    stop_criteria: master-done

    env:
    - NCCL_DEBUG=INFO

    commands:
    - |
        if [ $DSTACK_NODE_RANK -eq 0 ]; then
        mpirun \
            --allow-run-as-root \
            --hostfile $DSTACK_MPI_HOSTFILE \
            -n $DSTACK_GPUS_NUM \
            -N $DSTACK_GPUS_PER_NODE \
            --bind-to none \
            /opt/nccl-tests/build/all_reduce_perf -b 8 -e 8G -f 2 -g 1
        else
        sleep infinity
        fi

    resources:
    gpu: nvidia:1..8
    shm_size: 16GB
    ```

    If `startup_order` and `stop_criteria` are not configured (as in the PyTorch DDP example above), the master worker starts first and waits until all workers terminate. For MPI workloads, we need to change this.

#### Nodes and processes comparison

| | Slurm | dstack |
|---|-------|--------|
| **Nodes** | `--nodes=4` | `nodes: 4` |
| **Processes/tasks** | `--ntasks=8` or `--ntasks-per-node=2` (controls process distribution) | Determined by `commands` (relies on frameworks like `torchrun`, `accelerate`, `mpirun`, etc.) |

**Environment variables comparison:**

| Slurm | dstack | Purpose |
|-------|--------|---------|
| `SLURM_NODELIST` | `DSTACK_NODES_IPS` | Newline-delimited list of node IPs |
| `SLURM_NODEID` | `DSTACK_NODE_RANK` | Node rank (0-based) |
| `SLURM_PROCID` | N/A | Process rank (0-based, across all processes) |
| `SLURM_NTASKS` | `DSTACK_GPUS_NUM` | Total number of processes/GPUs |
| `SLURM_NTASKS_PER_NODE` | `DSTACK_GPUS_PER_NODE` | Number of processes/GPUs per node |
| `SLURM_JOB_NUM_NODES` | `DSTACK_NODES_NUM` | Number of nodes |
| Manual master address | `DSTACK_MASTER_NODE_IP` | Master node IP (automatically set) |
| N/A | `DSTACK_MPI_HOSTFILE` | Pre-populated MPI hostfile |

!!! info "Fleets"
    Distributed tasks may run only on a fleet with `placement: cluster` configured. Refer to [Partitions and fleets](#partitions-and-fleets) for configuration details.

## Queueing and scheduling

Both systems support core scheduling features and efficient resource utilization.

|  | Slurm | dstack |
|---------|-------|--------|
| **Prioritization** | Multi-factor system (fairshare, age, QOS); influenced via `--qos` or `--partition` flags | Set via `priority` (0-100); plus FIFO within the same priority |
| **Queueing** | Automatic via `sbatch`; managed through partitions | Set `on_events` to `[no-capacity]` under `retry` configuration |
| **Usage quotas** | Set via `sacctmgr` command per user/account/QOS | Not supported |
| **Backfill scheduling** | Enabled via `SchedulerType=sched/backfill` in `slurm.conf` | Not supported |
| **Preemption** | Configured via `PreemptType` in `slurm.conf` (QOS or partition-based) | Not supported |
| **Topology-aware scheduling** | Configured via `topology.conf` (InfiniBand switches, interconnects) | Not supported |

### Slurm

Slurm may use a multi-factor priority system, and limit usage across accounts, QOS, users, and single runs.

#### QOS

Quality of Service (QOS) provides a static priority boost. Administrators create QOS levels and assign them to users as defaults:

<div class="termy">

```shell
$ sacctmgr add qos high_priority Priority=1000
$ sacctmgr modify qos high_priority set MaxWall=200:00:00 MaxTRES=gres/gpu=8
```

</div>

Users can override the default QOS when submitting jobs via CLI (`sbatch --qos=high_priority`) or in the job script:

<div editor-title="train.sh">

```bash
#!/bin/bash
#SBATCH --qos=high_priority
```

</div>

#### Accounts and usage quotas

Usage quotas limit resource consumption and can be set per user, account, or QOS:

<div class="termy">

```shell
$ sacctmgr add account research
$ sacctmgr modify user user1 set account=research
$ sacctmgr modify user user1 set MaxWall=100:00:00 MaxTRES=gres/gpu=4
$ sacctmgr modify account research set MaxWall=1000:00:00 MaxTRES=gres/gpu=16
```

</div>

#### Monitoring commands

Slurm provides several CLI commands to check queue status, job details, and quota usage:

=== "Queue status"

    Use `squeue` to check queue status. Jobs are listed in scheduling order by priority:

    <div class="termy">

    ```shell
    $ squeue -u $USER
      JOBID PARTITION     NAME     USER ST  TIME  NODES REASON
      12345     gpu    training   user1 PD  0:00      2 Priority
    ```

    </div>

=== "Job details"

    Use `scontrol show job` to show detailed information about a specific job:

    <div class="termy">

    ```shell
    $ scontrol show job 12345
      JobId=12345 JobName=training
      UserId=user1(1001) GroupId=users(100)
      Priority=4294 Reason=Priority (Resources)
    ```

    </div>

=== "Quota usage"

    The `sacct` command can show quota consumption per user, account, or QOS depending on the format options:

    <div class="termy">

    ```shell
    $ sacct -S 2024-01-01 -E 2024-01-31 --format=User,Account,TotalCPU,TotalTRES
      User     Account   TotalCPU  TotalTRES
      user1    research  100:00:00 gres/gpu=50
    ```

    </div>

#### Topology-aware scheduling

Slurm detects network topology (InfiniBand switches, interconnects) and optimizes multi-node job placement to minimize latency. Configured in `topology.conf`, referenced from `slurm.conf`:

<div editor-title="/etc/slurm/topology.conf">

```bash
SwitchName=switch1 Nodes=node[01-10]
SwitchName=switch2 Nodes=node[11-20]
```

</div>

When scheduling multi-node jobs, Slurm prioritizes nodes connected to the same switch to minimize network latency.

### dstack

`dstack` doesn't have the concept of accounts, QOS, and doesn't support usage quotas yet.

#### Priority and retry policy

However, `dstack` supports prioritization (integer, no multi-factor or pre-emption) and queueing jobs.

<div editor-title=".dstack.yml">

```yaml
type: task
name: train-with-retry

python: 3.12
repos:
  - .

commands:
  - python train.py --batch-size=64

resources:
  gpu: 1
  memory: 32GB

# Priority: 0-100 (FIFO within same level; default: 0)
priority: 50

retry:
  on_events: [no-capacity]  # Retry until idle instances are available (enables queueing similar to Slurm)
  duration: 48h  # Maximum retry time (run age for no-capacity, time since last event for error/interruption)

max_duration: 2h
```

</div>

By default, the `retry` policy is not set, which means run fails immediately if no capacity is available.

#### Scheduled runs

Unlike Slurm, `dstack` supports scheduled runs using the `schedule` property with cron syntax, allowing tasks to start periodically at specific UTC times.

<div editor-title=".dstack.yml">

```yaml
type: task
name: task-with-cron

python: 3.12
repos:
  - .

commands:
  - python task.py --batch-size=64

resources:
  gpu: 1
  memory: 32GB

schedule:
  cron: "15 23 * * *" # everyday at 23:15 UTC
```

</div>

#### Monitoring commands

=== "Queue status"
    The `dstack ps` command displays runs and jobs sorted by priority, reflecting the order in which they will be scheduled.

    <div class="termy">

    ```shell
    $ dstack ps
      NAME          BACKEND  RESOURCES       PRICE    STATUS       SUBMITTED
      training-job  aws      H100:1 (spot)  $4.50    provisioning 2 mins ago
    ```

    </div>

#### Topology-aware scheduling

Topology-aware scheduling is not supported in `dstack`. While backend provisioning may respect network topology (e.g., cloud providers may provision instances with optimal inter-node connectivity), `dstack` task scheduling does not leverage topology-aware placement.

## Partitions and fleets

Partitions in Slurm and fleets in `dstack` both organize compute nodes for job scheduling. The key difference is that `dstack` fleets natively support dynamic cloud provisioning, whereas Slurm partitions organize pre-configured static nodes.

| | Slurm | dstack |
|---|-------|--------|
| **Provisioning** | Static nodes only | Supports both static clusters (SSH fleets) and dynamic provisioning via backends (cloud or Kubernetes) |
| **Overlap** | Nodes can belong to multiple partitions | Each instance belongs to exactly one fleet |
| **Accounts and projects** | Multiple accounts can use the same partition; used for quotas and resource accounting | Each fleet belongs to one project |

### Slurm

Slurm partitions are logical groupings of static nodes defined in `slurm.conf`. Nodes can belong to multiple partitions:

<div editor-title="slurm.conf">

```bash
PartitionName=gpu Nodes=gpu-node[01-10] Default=NO MaxTime=24:00:00
PartitionName=cpu Nodes=cpu-node[01-50] Default=YES MaxTime=72:00:00
PartitionName=debug Nodes=gpu-node[01-10] Default=NO MaxTime=1:00:00
```

</div>

Submit to a specific partition:

<div class="termy">

```shell
$ sbatch --partition=gpu train.sh
  Submitted batch job 12346
```

</div>

### dstack

`dstack` fleets are pools of instances (VMs or containers) that serve as both the organization unit and the provisioning template.

`dstack` supports two types of fleets:

| Fleet type | Description |
|------------|-------------|
| **Backend fleets** | Dynamically provisioned via configured backends (cloud or Kubernetes). Specify `resources` and `nodes` range; `dstack apply` provisions matching instances/clusters automatically. |
| **SSH fleets** | Use existing on-premises servers/clusters via `ssh_config`. `dstack apply` connects via SSH, installs dependencies. |

=== "Backend fleets"

    <div editor-title="fleet.dstack.yml">

    ```yaml
    type: fleet
    name: gpu-fleet

    nodes: 0..8

    resources:
      gpu: A100:80GB:8

    # Optional: Enables inter-node connectivity; required for distributed tasks
    placement: cluster

    # Optional: Split GPUs into blocks for multi-tenant sharing
    # Optional: Allows to share the instance across up to 8 workloads
    blocks: 8

    backends: [aws]

    # Spot instances for cost savings
    spot_policy: auto
    ```

    </div>

=== "SSH fleets"

    <div editor-title="fleet.dstack.yml">

    ```yaml
    type: fleet
    name: on-prem-gpu-fleet

    # Optional: Enables inter-node connectivity; required for distributed tasks
    placement: cluster

    # Optional: Allows to share the instance across up to 8 workloads
    blocks: 8

    ssh_config:
      user: dstack
      identity_file: ~/.ssh/id_rsa
      hosts:
        - gpu-node01.example.com
        - gpu-node02.example.com
      
      # Optional: Only required if hosts are behind a login node (bastion host)
      proxy_jump:
        hostname: login-node.example.com
        user: dstack
        identity_file: ~/.ssh/login_node_key
    ```

    </div>

Tasks with multiple nodes require a fleet with `placement: cluster` configured, otherwise they cannot run.

Submit to a specific fleet:

<div class="termy">

```shell
$ dstack apply -f train.dstack.yml --fleet gpu-fleet
  BACKEND  REGION    RESOURCES          SPOT  PRICE
  1  aws    us-east-1  4xCPU, 16GB, T4:1  yes   $0.10
  Submit the run train-model? [y/n]: y
  Launching `train-model`...
  ---> 100%
```

</div>

Create or update a fleet:

<div class="termy">

```shell
$ dstack apply -f fleet.dstack.yml
  Provisioning...
  ---> 100%
```

</div>

List fleets:

<div class="termy">

```shell
$ dstack fleet
  FLEET     INSTANCE  BACKEND              GPU             PRICE    STATUS  CREATED 
  gpu-fleet  0         aws (us-east-1)     A100:80GB (spot) $0.50   idle    3 mins ago
```

</div>

## Filesystems and data access

Both Slurm and `dstack` allow workloads to access filesystems (including shared filesystems) and copy files.

| | Slurm | dstack |
|---|-------|--------|
| **Host filesystem access** | Full access by default (native processes); mounting required only for containers | Always uses containers; requires explicit mounting via `volumes` (instance or network) |
| **Shared filesystems** | Assumes global namespace (NFS, Lustre, GPFS); same path exists on all nodes | Supported via SSH fleets with instance volumes (pre-mounted network storage); network volumes for backend fleets (limited support for shared filesystems) |
| **Instance disk size** | Fixed by cluster administrator | Configurable via `disk` property in `resources` (tasks) or fleet configuration; supports ranges (e.g., `disk: 500GB` or `disk: 200GB..1TB`) |
| **Local/temporary storage** | `$SLURM_TMPDIR` (auto-cleaned on job completion) | Container filesystem (auto-cleaned on job completion; except instance volumes or network volumes) |
| **File transfer** | `sbcast` for broadcasting files to allocated nodes | `repos` and `files` properties; `rsync`/`scp` via SSH (when attached) |

### Slurm

Slurm assumes a shared filesystem (NFS, Lustre, GPFS) with a global namespace. The same path exists on all nodes, and `$SLURM_TMPDIR` provides local scratch space that is automatically cleaned.

=== "Native processes"

    <div editor-title="train.sh">

    ```bash
    #!/bin/bash
    #SBATCH --nodes=4
    #SBATCH --gres=gpu:8
    #SBATCH --time=24:00:00

    # Global namespace - same path on all nodes
    # Dataset accessible at same path on all nodes
    DATASET_PATH=/shared/datasets/imagenet

    # Local scratch (faster I/O, auto-cleaned)
    # Copy dataset to local SSD for faster access
    cp -r $DATASET_PATH $SLURM_TMPDIR/dataset

    # Training with local dataset
    python train.py \
      --data=$SLURM_TMPDIR/dataset \
      --checkpoint-dir=/shared/checkpoints \
      --epochs=100

    # $SLURM_TMPDIR automatically cleaned when job ends
    # Checkpoints saved to shared filesystem persist
    ```

    </div>

=== "Containers"

    When using containers, shared filesystems must be explicitly mounted via bind mounts:

    <div editor-title="train.sh">

    ```bash
    #!/bin/bash
    #SBATCH --nodes=4
    #SBATCH --gres=gpu:8
    #SBATCH --time=24:00:00

    # Shared filesystem mounted at /datasets and /checkpoints
    DATASET_PATH=/datasets/imagenet

    # Local scratch accessible via $SLURM_TMPDIR (host storage mounted into container)
    # Copy dataset to local scratch, then train
    srun --container-image=/shared/images/pytorch-2.0-cuda11.8.sif \
      --container-mounts=/shared/datasets:/datasets,/shared/checkpoints:/checkpoints \
      cp -r $DATASET_PATH $SLURM_TMPDIR/dataset

    srun --container-image=/shared/images/pytorch-2.0-cuda11.8.sif \
      --container-mounts=/shared/datasets:/datasets,/shared/checkpoints:/checkpoints \
      python train.py \
        --data=$SLURM_TMPDIR/dataset \
        --checkpoint-dir=/checkpoints \
        --epochs=100

    # \$SLURM_TMPDIR automatically cleaned when job ends
    # Checkpoints saved to mounted shared filesystem persist
    ```

    </div>

#### File broadcasting (sbcast)

Slurm provides `sbcast` to distribute files efficiently using its internal network topology, avoiding filesystem contention:

<div editor-title="train.sh">

```bash
#!/bin/bash
#SBATCH --nodes=4
#SBATCH --ntasks=32

# Broadcast file to all allocated nodes
srun --ntasks=1 --nodes=1 sbcast /shared/data/input.txt /tmp/input.txt

# Use broadcasted file on all nodes
srun python train.py --input=/tmp/input.txt
```

</div>

### dstack

`dstack` supports both accessing filesystems (including shared filesystems) and uploading/downloading code/data from the client.

#### Instance volumes

Instance volumes mount host directories into containers. With distributed tasks, the host can use a shared filesystem (NFS, Lustre, GPFS) to share data across jobs within the same task:

<div editor-title=".dstack.yml">

```yaml
type: task
name: distributed-train

nodes: 4

python: 3.12
repos:
  - .

volumes:
  # Host directory (can be on shared filesystem) mounted into container
  - /mnt/shared/datasets:/data
  - /mnt/shared/checkpoints:/checkpoints

commands:
  - |
    torchrun \
      --nproc-per-node=$DSTACK_GPUS_PER_NODE \
      --node-rank=$DSTACK_NODE_RANK \
      --nnodes=$DSTACK_NODES_NUM \
      --master-addr=$DSTACK_MASTER_NODE_IP \
      --master-port=12345 \
      train.py \
      --data=/data \
      --checkpoint-dir=/checkpoints

resources:
  gpu: A100:80GB:8
  memory: 200GB
```

</div>

#### Network volumes

Network volumes are persistent cloud storage (AWS EBS, GCP persistent disks, RunPod volumes).

Single-node task:

<div editor-title=".dstack.yml">

```yaml
type: task
name: train-model

python: 3.9
repos:
  - .

volumes:
  - name: imagenet-dataset
    path: /data

commands:
  - python train.py --data=/data --batch-size=64

resources:
  gpu: 1
  memory: 32GB
```

</div>

Network volumes cannot be used with distributed tasks (no multi-attach support), except where multi-attach is supported (RunPod) or via volume interpolation. 

For distributed tasks, use interpolation to attach different volumes to each node.

<div editor-title=".dstack.yml">

```yaml
type: task
name: distributed-train

nodes: 4

python: 3.12
repos:
  - .

volumes:
  # Each node gets its own volume
  - name: dataset-${{ dstack.node_rank }}
    path: /data

commands:
  - |
    torchrun \
      --nproc-per-node=$DSTACK_GPUS_PER_NODE \
      --node-rank=$DSTACK_NODE_RANK \
      --nnodes=$DSTACK_NODES_NUM \
      --master-addr=$DSTACK_MASTER_NODE_IP \
      --master-port=12345 \
      train.py \
      --data=/data

resources:
  gpu: A100:80GB:8
  memory: 200GB
```

</div>

Volume name interpolation is not the same as a shared filesystem—each node has its own separate volume. `dstack` currently has limited support for shared filesystems when using backend fleets.

#### Repos and files

The `repos` and `files` properties allow uploading code or data into the container.

=== "Repos"

    The `repos` property clones Git repositories into the container. `dstack` clones the repo on the instance, applies local changes, and mounts it into the container. This is useful for code that needs to be version-controlled and synced.

    <div editor-title=".dstack.yml">

    ```yaml
    type: task
    name: train-model

    python: 3.9

    repos:
      - .  # Clone current directory repo

    commands:
      - python train.py --batch-size=64

    resources:
      gpu: 1
      memory: 32GB
      cpu: 8
    ```

    </div>

=== "Files"

    The `files` property mounts local files or directories into the container. Each entry maps a local path to a container path.

    <div editor-title=".dstack.yml">

    ```yaml
    type: task
    name: train-model

    python: 3.9

    files:
      - ../configs:~/configs
      - ~/.ssh/id_rsa:~/ssh/id_rsa

    commands:
      - python train.py --config ~/configs/model.yaml --batch-size=64

    resources:
      gpu: 1
      memory: 32GB
      cpu: 8
    ```

    </div>

    Files are uploaded to the instance and mounted into the container, but are not persisted across runs (2MB limit per file, configurable).

#### SSH file transfer

While attached to a run, you can transfer files via `rsync` or `scp` using the run name alias:

=== "rsync"

    <div class="termy">

    ```shell
    $ rsync -avz ./data/ <run name>:/path/inside/container/data/
    ```

    </div>

=== "scp"

    <div class="termy">

    ```shell
    $ scp large-dataset.h5 <run name>:/path/inside/container/
    ```

    </div>

> Uploading code/data from/to the client is not recommended as transfer speed greatly depends on network bandwidth between the CLI and the instance.

## Interactive development

Both Slurm and `dstack` allow allocating resources for interactive development.

| | Slurm | dstack |
|---|-------|--------|
| **Configuration** | Uses `salloc` command to allocate resources with a time limit; resources are automatically released when time expires | Uses `type: dev-environment` configurations as first-class citizen; provisions compute and runs until explicitly stopped (optional inactivity-based termination) |
| **IDE access** | Requires SSH access to allocated nodes | Native access using desktop IDEs (VS Code, Cursor, Windsurf, etc.) or SSH |
| **SSH access** | SSH to allocated nodes (host OS) using `SLURM_NODELIST` or `srun --pty` | SSH automatically configured; access via run name alias (inside container) |

### Slurm

Slurm uses `salloc` to allocate resources with a time limit. `salloc` returns a shell on the login node with environment variables set; use `srun` or SSH to access compute nodes. After the time limit expires, resources are automatically released:

<div class="termy">

```shell
$ salloc --nodes=1 --gres=gpu:1 --time=4:00:00
  salloc: Granted job allocation 12346

$ srun --pty bash
  [user@compute-node-01 ~]$ python train.py --epochs=1
  Training epoch 1...
  [user@compute-node-01 ~]$ exit
  exit

$ exit
  exit
  salloc: Relinquishing job allocation 12346
```

</div>

Alternatively, SSH directly to allocated nodes using hostnames from `SLURM_NODELIST`:

<div class="termy">

```shell
$ ssh $SLURM_NODELIST
  [user@compute-node-01 ~]$
```

</div>

### dstack

`dstack` uses `dev-environment` configuration type that automatically provisions an instance and runs until explicitly stopped, with optional inactivity-based termination. Access is provided via native desktop IDEs (VS Code, Cursor, Windsurf, etc.) or SSH:

<div editor-title="dev.dstack.yml">

```yaml
type: dev-environment
name: ml-dev

python: 3.12
ide: vscode

resources:
  gpu: A100:80GB:1
  memory: 200GB

# Optional: Maximum runtime duration (stops after this time)
max_duration: 8h

# Optional: Auto-stop after period of inactivity (no SSH/IDE connections)
inactivity_duration: 2h

# Optional: Auto-stop if GPU utilization is below threshold
utilization_policy:
  min_gpu_utilization: 10  # Percentage
  time_window: 1h
```

</div>

Start the dev environment:

<div class="termy">

```shell
$ dstack apply -f dev.dstack.yml
  BACKEND  REGION    RESOURCES                SPOT  PRICE
  1  runpod   CA-MTL-1  9xCPU, 48GB, A5000:24GB  yes   $0.11
  Submit the run ml-dev? [y/n]: y
  Launching `ml-dev`...
  ---> 100%
  To open in VS Code Desktop, use this link:
    vscode://vscode-remote/ssh-remote+ml-dev/workflow
```

</div>

#### Port forwarding

`dstack` tasks support exposing `ports` for running interactive applications like Jupyter notebooks or Streamlit apps:

=== "Jupyter"

    <div editor-title="jupyter.dstack.yml">

    ```yaml
    type: task
    name: jupyter

    python: 3.12

    commands:
      - pip install jupyterlab
      - jupyter lab --allow-root

    ports:
      - 8888

    resources:
      gpu: 1
      memory: 32GB
    ```

    </div>

=== "Streamlit"

    <div editor-title="streamlit.dstack.yml">

    ```yaml
    type: task
    name: streamlit-app

    python: 3.12

    commands:
      - pip install streamlit
      - streamlit hello

    ports:
      - 8501

    resources:
      gpu: 1
      memory: 32GB
    ```

    </div>

While `dstack apply` is attached, ports are automatically forwarded to `localhost` (e.g., `http://localhost:8888` for Jupyter, `http://localhost:8501` for Streamlit).

## Job arrays

### Slurm job arrays

Slurm provides native job arrays (`--array=1-100`) that create multiple job tasks from a single submission. Job arrays can be specified via CLI argument or in the job script.

<div class="termy">

```shell
$ sbatch --array=1-100 train.sh
  Submitted batch job 1001
```

</div>

Each task can use the `$SLURM_ARRAY_TASK_ID` environment variable within the job script to determine its configuration. Output files can use `%A` for the job ID and `%a` for the task ID in `#SBATCH --output` and `--error` directives.

### dstack

`dstack` does not support native job arrays. Submit multiple runs programmatically via CLI or API. Pass a custom environment variable (e.g., `TASK_ID`) to identify each run:

<div class="termy">

```shell
$ for i in {1..100}; do
    dstack apply -f train.dstack.yml \
      --name "train-array-task-${i}" \
      --env TASK_ID=${i} \
      --detach
  done
```

</div>


## Environment variables and secrets

Both Slurm and `dstack` handle sensitive data (API keys, tokens, passwords) for ML workloads. Slurm uses environment variables or files, while `dstack` provides encrypted secrets management in addition to environment variables.

### Slurm

Slurm uses OS-level authentication. Jobs run with the user's UID/GID and inherit the environment from the login node. No built-in secrets management; users manage credentials in their environment or shared files.

Set environment variables in the shell before submitting (requires `--export=ALL`):

<div class="termy">

```shell
$ export HF_TOKEN=$(cat ~/.hf_token)
$ sbatch --export=ALL train.sh
  Submitted batch job 12346
```

</div>

### dstack

In addition to environment variables (`env`), `dstack` provides a secrets management system with encryption. Secrets are referenced in configuration using `${{ secrets.name }}` syntax.

Set secrets:

<div class="termy">

```shell
$ dstack secret set huggingface_token <token>
$ dstack secret set wandb_api_key <key>
```

</div>

Use secrets in configuration:

<div editor-title=".dstack.yml">

```yaml
type: task
name: train-with-secrets

python: 3.12
repos:
  - .

env:
  - HF_TOKEN=${{ secrets.huggingface_token }}
  - WANDB_API_KEY=${{ secrets.wandb_api_key }}

commands:
  - pip install huggingface_hub
  - huggingface-cli download meta-llama/Llama-2-7b-hf
  - wandb login
  - python train.py

resources:
  gpu: A100:80GB:8
```

</div>

## Authentication

### Slurm

Slurm uses OS-level authentication. Users authenticate via SSH to login nodes using their Unix accounts. Jobs run with the user's UID/GID, ensuring user isolation—users cannot access other users' files or processes. Slurm enforces file permissions based on Unix UID/GID and association limits (MaxJobs, MaxSubmitJobs) configured per user or account.

### dstack

`dstack` uses token-based authentication. Users are registered within projects on the server, and each user is issued a token. This token is used for authentication with all CLI and API commands. Access is controlled at the project level with user roles:

| Role | Permissions |
|------|-------------|
| **Admin** | Can manage project settings, including backends, gateways, and members |
| **Manager** | Can manage project members but cannot configure backends and gateways |
| **User** | Can manage project resources including runs, fleets, and volumes |

`dstack` manages SSH keys on the server for secure access to runs and instances. User SSH keys are automatically generated and used when attaching to runs via `dstack attach` or `dstack apply`. Project SSH keys are used by the server to establish SSH connections to provisioned instances.

!!! note "Multi-tenancy isolation"
    `dstack` currently does not offer full isolation for multi-tenancy. Users may access global resources within the host.

## Monitoring and observability

Both systems provide tools to monitor job/run status, cluster/node status, resource metrics, and logs:

| | Slurm | dstack |
|---|-------|--------|
| **Job/run status** | `squeue` lists jobs in queue | `dstack ps` lists active runs |
| **Cluster/node status** | `sinfo` shows node availability | `dstack fleet` lists instances |
| **CPU/memory metrics** | `sstat` for running jobs | `dstack metrics` for real-time metrics |
| **GPU metrics** | Requires SSH to nodes, `nvidia-smi` per node | Automatic collection via `nvidia-smi`/`amd-smi`, `dstack metrics` |
| **Job history** | `sacct` for completed jobs | `dstack ps -n NUM` shows run history |
| **Logs** | Written to files (`--output`, `--error`) | Streamed via API, `dstack logs` |

### Slurm

Slurm provides command-line tools for monitoring cluster state, jobs, and history.

Check node status:

<div class="termy">

```shell
$ sinfo
  PARTITION AVAIL  TIMELIMIT  NODES  STATE NODELIST
  gpu          up  1-00:00:00     10   idle gpu-node[01-10]
```

</div>

Check job queue:

<div class="termy">

```shell
$ squeue -u $USER
  JOBID PARTITION     NAME     USER ST  TIME  NODES
  12345     gpu    training   user1  R  2:30      2
```

</div>

Check job details:

<div class="termy">

```shell
$ scontrol show job 12345
  JobId=12345 JobName=training
  UserId=user1(1001) GroupId=users(100)
  NumNodes=2 NumCPUs=64 NumTasks=32
  Gres=gpu:8(IDX:0,1,2,3,4,5,6,7)
```

</div>

Check resource usage for running jobs (`sstat` only works for running jobs):

<div class="termy">

```shell
$ sstat --job=12345 --format=JobID,MaxRSS,MaxVMSize,CPUUtil
        JobID     MaxRSS  MaxVMSize   CPUUtil
  12345.0        2048M     4096M      95.2%
```

</div>

Check GPU usage (requires SSH to node):

<div class="termy">

```shell
$ srun --jobid=12345 --pty nvidia-smi
  GPU 0: 95% utilization, 72GB/80GB memory
```

</div>

Check job history for completed jobs:

<div class="termy">

```shell
$ sacct --job=12345 --format=JobID,Elapsed,MaxRSS,State,ExitCode
        JobID    Elapsed     MaxRSS      State ExitCode
  12345     2:30:00     2048M  COMPLETED      0:0
```

</div>

View logs (written to files via `--output` and `--error` flags; typically in the submission directory on a shared filesystem):

<div class="termy">

```shell
$ cat slurm-12345.out
  Training started...
  Epoch 1/10: loss=0.5
```

</div>

If logs are on compute nodes, find the node from `scontrol show job`, then access via `srun --jobid` (running jobs) or SSH (completed jobs):

<div class="termy">

```shell
$ srun --jobid=12345 --nodelist=gpu-node01 --pty bash
$ cat slurm-12345.out
```

</div>

### dstack

`dstack` automatically collects essential metrics (CPU, memory, GPU utilization) using vendor utilities (`nvidia-smi`, `amd-smi`, etc.) and provides real-time monitoring via CLI.

List runs:

<div class="termy">

```shell
$ dstack ps
  NAME          BACKEND  GPU             PRICE    STATUS       SUBMITTED
  training-job  aws      H100:1 (spot)   $4.50    running      5 mins ago
```

</div>

List fleets and instances (shows GPU health status):

<div class="termy">

```shell
$ dstack fleet
  FLEET     INSTANCE  BACKEND          RESOURCES  STATUS          PRICE   CREATED
  my-fleet  0         aws (us-east-1)  T4:16GB:1  idle            $0.526  11 mins ago
            1         aws (us-east-1)  T4:16GB:1  idle (warning) $0.526  11 mins ago
```

</div>

Check real-time metrics:

<div class="termy">

```shell
$ dstack metrics training-job
  NAME             STATUS  CPU  MEMORY          GPU
  training-job     running 45%  16.27GB/200GB   gpu=0 mem=72.48GB/80GB util=95%
```

</div>

Stream logs (stored centrally using external storage services like CloudWatch Logs or GCP Logging, accessible via CLI and UI):

<div class="termy">

```shell
$ dstack logs training-job
  Training started...
  Epoch 1/10: loss=0.5
```

</div>

#### Prometheus integration

`dstack` exports additional metrics to Prometheus:

| Metric type | Description |
|-------------|-------------|
| **Fleet metrics** | Instance duration, price, GPU count |
| **Run metrics** | Run counters (total, terminated, failed, done) |
| **Job metrics** | Execution time, cost, CPU/memory/GPU usage |
| **DCGM telemetry** | Temperature, ECC errors, PCIe replay counters, NVLink errors |
| **Server health** | HTTP request metrics |

To enable Prometheus export, set the `DSTACK_ENABLE_PROMETHEUS_METRICS` environment variable and configure Prometheus to scrape metrics from `<dstack server URL>/metrics`.

> GPU health monitoring is covered in the [GPU health monitoring](#gpu-health-monitoring) section below.

## Fault tolerance, checkpointing, and retry

Both systems support fault tolerance for long-running training jobs that may be interrupted by hardware failures, spot instance terminations, or other issues:

| | Slurm | dstack |
|---|-------|--------|
| **Retry** | `--requeue` flag requeues jobs on node failure (hardware crash) or preemption, not application failures (software crashes); all nodes requeued together (all-or-nothing) | `retry` property with `on_events` (`error`, `interruption`) and `duration`; all jobs stopped and run resubmitted if any job fails (all-or-nothing) |
| **Graceful stop** | Grace period with `SIGTERM` before `SIGKILL`; `--signal` sends signal before time limit (e.g., `--signal=B:USR1@300`) | Not supported |
| **Checkpointing** | Application-based; save to shared filesystem | Application-based; save to persistent volumes |
| **Instance health** | `HealthCheckProgram` in `slurm.conf` runs custom scripts (DCGM/RVS); non-zero exit drains node (excludes from new scheduling, running jobs continue) | Automatic GPU health monitoring via DCGM; unhealthy instances excluded from scheduling |

### Slurm

Slurm handles three types of failures: system failures (hardware crash), application failures (software crash), and preemption.

Enable automatic requeue on node failure (not application failures). For distributed jobs, if one node fails, the entire job is requeued (all-or-nothing):

<div editor-title="train.sh">

```bash
#!/bin/bash
#SBATCH --job-name=train-with-checkpoint
#SBATCH --nodes=4
#SBATCH --gres=gpu:8
#SBATCH --time=48:00:00
#SBATCH --requeue  # Requeue on node failure only

srun python train.py
```

</div>

Preempted jobs receive `SIGTERM` during a grace period before `SIGKILL` and are typically requeued automatically. Use `--signal` to send a custom signal before the time limit expires:

<div editor-title="train.sh">

```bash
#!/bin/bash
#SBATCH --job-name=train-with-checkpoint
#SBATCH --nodes=4
#SBATCH --gres=gpu:8
#SBATCH --time=48:00:00
#SBATCH --signal=B:USR1@300  # Send USR1 5 minutes before time limit

trap 'python save_checkpoint.py --checkpoint-dir=/shared/checkpoints' USR1

if [ -f /shared/checkpoints/latest.pt ]; then
  RESUME_FLAG="--resume /shared/checkpoints/latest.pt"
fi

srun python train.py \
  --checkpoint-dir=/shared/checkpoints \
  $RESUME_FLAG
```

</div>

Checkpoints are saved to a shared filesystem. Applications must implement checkpointing logic.

Custom health checks are configured via `HealthCheckProgram` in `slurm.conf`:

<div editor-title="slurm.conf">

```bash
HealthCheckProgram=/shared/scripts/gpu_health_check.sh
```

</div>

The health check script should exit with non-zero code to drain the node:

<div editor-title="gpu_health_check.sh">

```bash
#!/bin/bash
dcgmi diag -r 1
if [ $? -ne 0 ]; then
    exit 1  # Non-zero exit drains node
fi
```

</div>

Drained nodes are excluded from new scheduling, but running jobs continue until completion.

### dstack

`dstack` handles three types of failures: provisioning failures (`no-capacity`), job failures (`error`), and interruptions (`interruption`). The `error` event is triggered by application failures (non-zero exit code) and instance unreachable issues. The `interruption` event is triggered by spot instance terminations and network/hardware issues.

By default, runs fail immediately. Enable retry via the `retry` property to handle these events:

<div editor-title=".dstack.yml">

```yaml
type: task
name: train-with-checkpoint-retry

nodes: 4

python: 3.12
repos:
  - .

volumes:
  # Use instance volumes (host directories) or network volumes (cloud-managed persistent storage)
  - name: checkpoint-volume
    path: /checkpoints

commands:
  - |
    if [ -f /checkpoints/latest.pt ]; then
      RESUME_FLAG="--resume /checkpoints/latest.pt"
    fi
    python train.py \
      --checkpoint-dir=/checkpoints \
      $RESUME_FLAG

resources:
  gpu: A100:80GB:8
  memory: 200GB

spot_policy: auto

retry:
  on_events: [error, interruption]
  duration: 48h
```

</div>

For distributed tasks, if any job fails and retry is enabled, all jobs are stopped and the run is resubmitted (all-or-nothing).

Unlike Slurm, `dstack` does not support graceful shutdown signals. Applications must implement proactive checkpointing (periodic saves) and check for existing checkpoints on startup to resume after retries.

## GPU health monitoring

Both systems monitor GPU health to prevent degraded hardware from affecting workloads:

| | Slurm | dstack |
|---|-------|--------|
| **Health checks** | Custom scripts (DCGM/RVS) via `HealthCheckProgram` in `slurm.conf`; typically active diagnostics (`dcgmi diag`) or passive health watches | Automatic DCGM health watches (passive, continuous monitoring) |
| **Failure handling** | Non-zero exit drains node (excludes from new scheduling, running jobs continue); status: DRAIN/DRAINED | Unhealthy instances excluded from scheduling; status shown in `dstack fleet`: `idle` (healthy), `idle (warning)`, `idle (failure)` |

### Slurm

Configure custom health check scripts via `HealthCheckProgram` in `slurm.conf`. Scripts typically use DCGM diagnostics (`dcgmi diag`) for NVIDIA GPUs or RVS for AMD GPUs:

<div editor-title="slurm.conf">

```bash
HealthCheckProgram=/shared/scripts/gpu_health_check.sh
```

</div>

<div editor-title="gpu_health_check.sh">

```bash
#!/bin/bash
dcgmi diag -r 1  # DCGM diagnostic for NVIDIA GPUs
if [ $? -ne 0 ]; then
    exit 1  # Non-zero exit drains node
fi
```

</div>

Drained nodes are excluded from new scheduling, but running jobs continue until completion.

### dstack

`dstack` automatically monitors GPU health using DCGM background health checks on instances with NVIDIA GPUs. Supported on cloud backends where DCGM is pre-installed automatically (or comes with users' `os_images`) and SSH fleets where DCGM packages (`datacenter-gpu-manager-4-core`, `datacenter-gpu-manager-4-proprietary`, `datacenter-gpu-manager-exporter`) are installed on hosts.

> AMD GPU health monitoring is not supported yet.

Health status is displayed in `dstack fleet`:

<div class="termy">

```shell
$ dstack fleet
  FLEET     INSTANCE  BACKEND          RESOURCES  STATUS          PRICE   CREATED
  my-fleet  0         aws (us-east-1)  T4:16GB:1  idle            $0.526  11 mins ago
            1         aws (us-east-1)  T4:16GB:1  idle (warning)  $0.526  11 mins ago
            2         aws (us-east-1)  T4:16GB:1  idle (failure)  $0.526  11 mins ago
```

</div>

Health status:

| Status | Description |
|--------|-------------|
| `idle` | Healthy, no issues detected |
| `idle (warning)` | Non-fatal issues (e.g., correctable ECC errors); instance still usable |
| `idle (failure)` | Fatal issues (uncorrectable ECC, PCIe failures); instance excluded from scheduling |

GPU health metrics are also exported to Prometheus (see [Prometheus integration](#prometheus-integration)).

## Job dependencies

Job dependencies enable chaining tasks together, ensuring that downstream jobs only run after upstream jobs complete.

### Slurm dependencies

Slurm provides native dependency support via `--dependency` flags. Dependencies are managed by Slurm:

| Dependency type | Description |
|----------------|-------------|
| **`afterok`** | Runs only if the dependency job finishes with Exit Code 0 (success) |
| **`afterany`** | Runs regardless of success or failure (useful for cleanup jobs) |
| **`aftercorr`** | For array jobs, allows corresponding tasks to start as soon as the matching task in the dependency array completes (e.g., Task 1 of Array B starts when Task 1 of Array A finishes, without waiting for the entire Array A) |
| **`singleton`** | Based on job name and user (not job IDs), ensures only one job with the same name runs at a time for that user (useful for serializing access to shared resources) |

Submit a job that depends on another job completing successfully:

<div class="termy">

```shell
$ JOB_TRAIN=$(sbatch train.sh | awk '{print $4}')
  Submitted batch job 1001

$ sbatch --dependency=afterok:$JOB_TRAIN evaluate.sh
  Submitted batch job 1002
```

</div>

Submit a job with singleton dependency (only one job with this name runs at a time):

<div class="termy">

```shell
$ sbatch --job-name=ModelTraining --dependency=singleton train.sh
  Submitted batch job 1004
```

</div>

### dstack { #dstack-workflow-orchestration }

`dstack` does not support native job dependencies. Use external workflow orchestration tools (Airflow, Prefect, etc.) to implement dependencies.

=== "Prefect"

    ```python
    from prefect import flow, task
    import subprocess

    @task
    def train_model():
        """Submit training job and wait for completion"""
        subprocess.run(
            ["dstack", "apply", "-f", "train.dstack.yml", "--name", "train-run"],
            check=True  # Raises exception if training fails
        )
        return "train-run"

    @task
    def evaluate_model(run_name):
        """Submit evaluation job after training succeeds"""
        subprocess.run(
            ["dstack", "apply", "-f", "evaluate.dstack.yml", "--name", f"eval-{run_name}"],
            check=True
        )

    @flow
    def ml_pipeline():
        train_run = train_model()
        evaluate_model(train_run)
    ```

=== "Airflow"

    ```python
    from airflow.decorators import dag, task
    from datetime import datetime
    import subprocess

    @dag(schedule=None, start_date=datetime(2024, 1, 1), catchup=False)
    def ml_training_pipeline():
        @task
        def train(context):
            """Submit training job and wait for completion"""
            run_name = f"train-{context['ds']}"
            subprocess.run(
                ["dstack", "apply", "-f", "train.dstack.yml", "--name", run_name],
                check=True  # Raises exception if training fails
            )
            return run_name
        
        @task
        def evaluate(run_name, context):
            """Submit evaluation job after training succeeds"""
            eval_name = f"eval-{run_name}"
            subprocess.run(
                ["dstack", "apply", "-f", "evaluate.dstack.yml", "--name", eval_name],
                check=True
            )
        
        # Define task dependencies - train() completes before evaluate() starts
        train_run = train()
        evaluate(train_run)

    ml_training_pipeline()
    ```

## Heterogeneous jobs

Heterogeneous jobs (het jobs) allow a single job to request different resource configurations for different components (e.g., GPU nodes for training, high-memory CPU nodes for preprocessing). This is an edge case used for coordinated multi-component workflows.

### Slurm

Slurm supports heterogeneous jobs via `#SBATCH hetjob` and `--het-group` flags. Each component can specify different resources:

```bash
#!/bin/bash
#SBATCH --job-name=ml-pipeline
#SBATCH hetjob
#SBATCH --het-group=0 --nodes=2 --gres=gpu:8 --mem=200G
#SBATCH --het-group=1 --nodes=1 --mem=500G --partition=highmem

# Use SLURM_JOB_COMPONENT_ID to identify the component
if [ "$SLURM_JOB_COMPONENT_ID" -eq 0 ]; then
    srun python train.py
elif [ "$SLURM_JOB_COMPONENT_ID" -eq 1 ]; then
    srun python preprocess.py
fi
```

### dstack

`dstack` does not support heterogeneous jobs natively. Use separate runs with [workflow orchestration tools (Prefect, Airflow)](#dstack-workflow-orchestration) or submit multiple runs programmatically to coordinate components with different resource requirements.
