# Spark

This example shows how use `dstack` to spin up an [Apache Spark](https://spark.apache.org/docs/latest/index.html) cluster and run tasks on it.

## Create fleet

First create a fleet for the Spark cluster. We'll use one instance as the Spark master node and one instance as the Spark worker node. We'll also provision a third instance that we'll use to submit Spark apps to the cluster so that we don't need to run anything locally:

```yaml
type: fleet
name: spark-fleet
nodes: 3
placement: cluster
backends: [gcp]
```

```shell
dstack apply -f fleet.dstack.yaml
```

## Launch Spark cluster

The following `dstack` task launches Spark master and worker nodes. `dstack` makes the cluster UI available at `localhost:8080`, and Spark apps can be submitted to `localhost:7077`.

```yaml
type: task
name: spark-cluster
image: spark
nodes: 2
commands:
  - export SPARK_MASTER_HOST=$DSTACK_MASTER_NODE_IP
  - export SPARK_NO_DAEMONIZE=true
  - if [ $DSTACK_NODE_RANK = 0 ]; then /opt/spark/sbin/start-master.sh; else /opt/spark/sbin/start-worker.sh spark://$DSTACK_MASTER_NODE_IP:7077; fi
ports:
  - 7077
  - 8080
```

```shell
dstack apply -f cluster.dstack.yaml
```

## Run Spark app

If you have Spark installed locally, you can submit your code directly to `localhost:7077`. In this example, we run another `dstack` task to submit code to the Spark cluster. You should provide it with `SPARK_CLUSTER_IP` set to the IP address of the Spark cluster master node. (You can find it in the output of `dstack apply -f cluster.dstack.yaml`.)

```yaml
type: task
name: spark-task
image: spark
env:
  - SPARK_CLUSTER_IP
commands:
  - pip install pyspark
  - python3 tasks/words.py
```

```shell
export SPARK_CLUSTER_IP=

dstack apply -f task.dstack.yaml
```
