# Ray

This example shows how use `dstack` to spin up a [Ray](https://docs.ray.io/en/latest/ray-overview/index.html) cluster and run Ray jobs on it.

## Create fleet

First create a fleet for the Ray cluster. We'll use one instance for a master node and three instances for worker nodes:

```yaml
type: fleet
name: ray-fleet
nodes: 4
placement: cluster
backends: [gcp]
resources: 
  cpu: 8..
  memory: 32GB..
  gpu: 1
```

```shell
dstack apply -f fleet.dstack.yaml
```

## Launch Ray cluster

The following `dstack` task launches Ray master and worker nodes.
`dstack` makes the Ray dashboard available at `localhost:8265`.

```yaml
type: task
name: ray-cluster
nodes: 4
commands:
  - pip install -U "ray[default]"
  - |
    if [ $DSTACK_NODE_RANK = 0 ]; then 
      ray start --head --port=6379;
    else
      ray start --address=$DSTACK_MASTER_NODE_IP:6379
    fi
ports:
  - 8265 # ray dashboard port
resources:
  shm_size: 8GB
```

```shell
dstack apply -f cluster.dstack.yaml
```

## Run Ray jobs

Install Ray locally:

```shell
pip install ray
```

Now you can submit Ray jobs to the cluster available at `localhost:8265`:

```shell
RAY_ADDRESS='http://localhost:8265' ray job submit \
--working-dir . \
--runtime-env-json='{"pip": ["ray[train]", "torch", "torchvision", "tqdm", "filelock"]}' \
-- python tasks/pytorch-mnist.py
```

See more examples in the [Ray docs](https://docs.ray.io/en/latest/train/examples.html).

Using Ray via `dstack` is a powerful way to get access to the rich Ray ecosystem while benefiting from `dstack`'s provisioning capabilities.
