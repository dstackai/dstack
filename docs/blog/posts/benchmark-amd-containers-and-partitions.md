---
title: "Benchmarking AMD GPUs: bare-metal, containers, partitions"
date: 2025-07-15
description: "TBA"
slug: benchmark-amd-containers-and-partitions
image: https://dstack.ai/static-assets/static-assets/images/benchmark-amd-containers-and-partitions.png
categories:
  - Benchmarks
---

# Benchmarking AMD GPUs: bare-metal, containers, partitions

Our new benchmark explores two important areas for optimizing AI workloads on AMD GPUs: First, do containers introduce a performance penalty for network-intensive tasks compared to a bare-metal setup? Second, how does partitioning a powerful GPU like the MI300X affect its real-world performance for different types of AI workloads?

<img src="https://dstack.ai/static-assets/static-assets/images/benchmark-amd-containers-and-partitions.png" width="630"/>

<!-- more -->

This benchmark was supported by [Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"},
a provider of AMD GPU bare-metal and VM infrastructure.

## Benchmark 1: Bare-metal vs containers

### Finding 1: No loss in interconnect bandwidth

A common concern is that the abstraction layer of containers might slow down communication between GPUs on different nodes. To test this, we measured interconnect performance using two critical methods: high-level RCCL collectives (AllGather, AllReduce) essential for distributed AI, and low-level RDMA write tests for a raw measure of network bandwidth.

#### AllGather

The `all_gather` operation is crucial for tasks like tensor-parallel inference, where results from multiple GPUs must be combined. Our tests showed that container performance almost perfectly matched bare-metal across message sizes from 8MB to 16GB. 

<img src="https://dstack.ai/static-assets/static-assets/images/benchmark-amd-containers-and-partitions-chart1a.png" width="750"/>

#### AllReduce

Similarly, `all_reduce` is the backbone of distributed training, used for synchronizing gradients. Once again, the results were clear: containers performed just as well as bare-metal.

<img src="https://dstack.ai/static-assets/static-assets/images/benchmark-amd-containers-and-partitions-chart2a.png" width="750"/>

Both bare-metal and container setups achieved nearly identical peak bus bandwidth (around 350 GB/s for 16GB messages), confirming that containerization does not hinder this fundamental collective operation.

??? info "Variability"
    Both setups showed some variability at smaller message sizes—typical behavior due to kernel launch latencies—but converged to stable, identical peak bandwidths for larger transfers. The fluctuations at smaller sizes are likely caused by non-deterministic factors such as CPU-induced pauses during GPU kernel launches, occasionally favoring one setup over the other.

#### RDMA write

To isolate the network from any framework overhead, we ran direct device-to-device RDMA write tests. This measures the raw data transfer speed between GPUs in different nodes. 

<img src="https://dstack.ai/static-assets/static-assets/images/benchmark-amd-containers-and-partitions-chart3a.png" width="750"/>

The results were definitive: bidirectional bandwidth was virtually identical in both bare-metal and container environments across all message sizes, from a tiny 2 bytes up to 8MB.

#### Conclusion

Our experiments consistently demonstrate that running multi-node AI workloads inside containers does not degrade interconnect performance. The performance of RCCL collectives and raw RDMA bandwidth on AMD GPUs is on par with a bare-metal configuration. This debunks the myth of a "container tax" and validates containers as a first-class choice for scalable AI infrastructure.

## Benchmark 2: Partition performance isolated vs mesh

The AMD GPU can be [partitioned :material-arrow-top-right-thin:{ .external }](https://instinct.docs.amd.com/projects/amdgpu-docs/en/latest/gpu-partitioning/mi300x/overview.html){:target="_blank"} into smaller, independent units (e.g., NPS4 mode splits one GPU into four partitions). This promises better memory bandwidth utilization. Does this theoretical gain translate to better performance in practice?

### Finding 1: Higher performance for isolated partitions

First, we sought to reproduce and extend findings from the [official ROCm blog :material-arrow-top-right-thin:{ .external }](https://rocm.blogs.amd.com/software-tools-optimization/compute-memory-modes/README.html){:target="_blank"}. We benchmarked the memory bandwidth of a single partition (in CPX/NPS4 mode) against a full, unpartitioned GPU (in SPX/NPS1 mode).

<img src="https://dstack.ai/static-assets/static-assets/images/benchmark-amd-containers-and-partitions-chart4a.png" width="750"/>

Our results confirmed that a single partition offers superior memory bandwidth. After aggregating the results to ensure an apples-to-apples comparison, we found the partitioned mode delivered consistently higher memory bandwidth across all message sizes, with especially large gains in the 32MB to 128MB range.

### Finding 2: Worse performance for partition meshes

Our benchmark showed that isolated partitions in CPX/NPS4 mode deliver strong memory bandwidth. But can these partitions work efficiently together in mesh scenarios? If performance drops when partitions communicate or share load, the GPU loses significant value for real-world workloads.

#### Data-parallel inference

We ran eight independent vLLM instances on eight partitions of a single MI300X and compared their combined throughput against one vLLM instance on a single unpartitioned GPU. The single GPU was significantly faster, and the performance gap widened as the request rate increased. The partitions were starved for memory, limiting their ability to handle the KV cache for a high volume of requests.

<img src="https://dstack.ai/static-assets/static-assets/images/benchmark-amd-containers-and-partitions-chart5a.png" width="750"/>

The degradation stems from increased memory pressure, as each partition has only a fraction of GPU memory, limiting its ability to handle larger workloads efficiently.

#### Tensor-parallel inference

We built a toy inference benchmark with PyTorch’s native distributed support to simulate Tensor Parallelism. A single GPU in SPX/NPS1 mode significantly outperformed the combined throughput of 8xCPX/NPS4 partitions.

<img src="https://dstack.ai/static-assets/static-assets/images/benchmark-amd-containers-and-partitions-chart6a.png" width="750"/>

The gap stems from the overhead of collective operations like `all_gather`, which are needed to synchronize partial outputs across GPU partitions.

#### Conclusion

Although GPU partitioning provides a memory bandwidth boost in isolated microbenchmarks, this benefit does not carry over to practical inference scenarios.

In reality, performance is limited by two factors:

1. **Reduced memory**: Each partition has only a fraction of the GPU's total HBM, creating a bottleneck for memory-hungry tasks like storing KV caches.
2. **Communication overhead**: When partitions must work together, the cost of communication between them negates the performance gains.

GPU partitioning is only practical if used dynamically—for instance, to run multiple small development jobs or lightweight models, and then "unfractioning" the GPU back to its full power for larger, more demanding workloads.

#### Limitations

1. **Reproducibility**: AMD’s original blog post on partitioning lacked detailed setup information, so we had to reconstruct the benchmarks independently.
2. **Network tuning**: These benchmarks were run on a default, out-of-the-box network configuration. Our results for RCCL (~339 GB/s) and RDMA (~726 Gbps) are slightly below the peak figures [reported by Dell :material-arrow-top-right-thin:{ .external }](https://infohub.delltechnologies.com/en-us/l/generative-ai-in-the-enterprise-with-amd-accelerators/rccl-and-perftest-for-cluster-validation-1/4/){:target="_blank"}. This suggests that further performance could be unlocked with expert tuning of network topology, MTU size, and NCCL environment variables.

## Benchmark setup

### Hardware configuration

Two nodes with below specifications:

* Dell PowerEdge XE9680 (MI300X)
* CPU: 2 x Intel Xeon Platinum 8462Y+
* RAM: 2.0 TiB
* GPU: 8 x AMD MI300X
* OS: Ubuntu 22.04.5 LTS
* ROCm: 6.4.1
* AMD SMI: 25.4.2+aca1101

### Benchmark methodology

The full, reproducible steps are available in our GitHub repository. Below is a summary of the approach.

#### Creating a fleet

We first defined a `dstack` [SSH fleet](../../docs/concepts/fleets.md#ssh) to manage the two-node cluster.

```yaml
type: fleet
name: hotaisle-fleet
placement: any
ssh_config:
  user: hotaisle
  identity_file: ~/.ssh/id_rsa
  hosts:
    - hostname: ssh.hotaisle.cloud
      port: 22007
    - hostname: ssh.hotaisle.cloud
      port: 22015
```

#### Bare-metal

**RCCL tests**

1. Install OpenMPI:

```shell
apt install libopenmpi-dev openmpi-bin
```

2. Clone the RCCL tests repository

```shell
git clone https://github.com/ROCm/rccl-tests.git
```

3. Build RCCL tests

```shell
cd rccl-tests
make MPI=1 MPI_HOME=$OPEN_MPI_HOME
```

4. Create a hostfile with node IPs

```shell
cat > hostfile <<EOF
100.64.129.30 slots=8
100.64.129.62 slots=8
EOF
```

1. Run RCCL tests

```shell
mpirun --allow-run-as-root \
  --hostfile hostfile \
  -N 8 \
  -n 16 \
  --mca plm_rsh_args "-p 22 -l hotaisle" \
  --mca btl_tcp_if_include bond0 \
  -x NCCL_IB_GID_INDEX=3 \
  -x NCCL_IB_DISABLE=0 \
  ./build/all_gather_perf -b 4 -e 16G -f 2 -g 1 -w 5 --iters 100 -c 0
```

**RDMA write**

1. Clone the performance tests repository

```shell
git clone https://github.com/linux-rdma/perftest
```

2. Build performance tests

```shell
cd perftest
./autogen.sh
./configure
make & make install
```

3. Run the server in one node

```shell
taskset -c 0-31 ./ib_write_bw -d rocep28s0 -F -a --report_gbits -q 2
```

4. Run the client on the other node

```shell
taskset -c 0-31 ./ib_write_bw -d rocep28s0 -F -a --report_gbits -q $SERVER_IP_ADDRESS
```

#### Containers

For the container experiments we used a `dstack`’s [distributed task](../../docs/concepts/tasks.md#distributed-tasks).

**RCCL tests**

1. Define a task configuration

```yaml
type: task
name: rccl-tests

nodes: 2
startup_order: workers-first
stop_criteria: master-done

# Mount the system libraries folder from the host
volumes:
  - /usr/local/lib:/mnt/lib

image: rocm/dev-ubuntu-22.04:6.4-complete
env:
  # - NCCL_DEBUG=INFO
  - OPEN_MPI_HOME=/usr/lib/x86_64-linux-gnu/openmpi
commands:
  # Setup MPI and build RCCL tests
  - apt-get install -y git libopenmpi-dev openmpi-bin
  - git clone https://github.com/ROCm/rccl-tests.git
  - cd rccl-tests
  - make MPI=1 MPI_HOME=$OPEN_MPI_HOME

  # Preload the RoCE driver library from the host (for Broadcom driver compatibility)
  - export LD_PRELOAD=/mnt/lib/libbnxt_re-rdmav34.so
  # Run RCCL tests via MPI
  - |
    if [ $DSTACK_NODE_RANK -eq 0 ]; then
      mpirun --allow-run-as-root \
        --hostfile $DSTACK_MPI_HOSTFILE \
        -n $DSTACK_GPUS_NUM \
        -N $DSTACK_GPUS_PER_NODE \
        --mca btl_tcp_if_include bond0 \
        -x LD_PRELOAD \
        -x NCCL_IB_GID_INDEX=3 \
        -x NCCL_IB_DISABLE=0 \
        ./build/all_reduce_perf -b 4 -e 16G -f 2 -g 1 -w 5 --iters 100 -c 0;
    else
      sleep infinity
    fi

resources:
  gpu: MI300X:8
```

**Performance tests**

1. Define a task configuration

```yaml
type: task
name: perf-tests

nodes: 2
startup_order: master-first
stop_criteria: all-done


# Mount the system libraries folder from the host
volumes:
  - /usr/local/lib:/mnt/lib

image: rocm/dev-ubuntu-22.04:6.4-complete

commands:
  # Build perf tests
  - git clone https://github.com/linux-rdma/perftest
  - cd perftest
  - ./autogen.sh
  - ./configure
  - make & make install
  # Preload the RoCE driver library from the host (for Broadcom driver     compatibility) 
  - export LD_PRELOAD=/mnt/lib/libbnxt_re-rdmav34.so
  - |
    # Run server in master node
    if [ $DSTACK_NODE_RANK -eq 0 ]; then
      taskset -c 0-31 ./ib_write_bw -d rocep28s0 -F -a --report_gbits -q 2
    else
      # Run client in worker node
      taskset -c 0-31 ./ib_write_bw -d rocep28s0 -F -a --report_gbits -q 2 $DSTACK_MASTER_NODE_IP
    fi

resources:
  gpu: MI300X:8
```

2. Run the task

```shell
dstack apply -f perf.dstack.yml
```

To enable the bidirectional mode, add the `-b` flag to both the server and client commands.
To enable device-to-device mode, add the `--use_rocm=0` flag to both the server and client commands.

3. Run the task

```shell
dstack apply -f rccl.dstack.yml
```

For `all_reduce`, replace `all_gather_perf` with `all_reduce_perf`. `all_gather` and `all_reduce` tests are run 10 times to obtain bandwidth data for deviation calculation.

#### Partitions

To test partitioning, we first set the GPU to NPS4 mode on bare-metal using `amd-smi`.

```shel
sudo amd-smi set --memory-partition NPS4
```

**Stream benchmark**

1. Clone the benchmark repo

```shell
git clone https://github.com/dstackai/benchmarks.git
```

2. Run the benchmarks

```
cd benchmarks
git checkout amd_partitions_benchmark
python3 amd/partitions/benchmark_stream.py --size $SIZE
```

The `SIZE` value is `1M`, `2M`, .., `8G`.

**vLLM data parallel**

1. Build nginx container (see [vLLM-nginx :material-arrow-top-right-thin:{ .external }](https://docs.vllm.ai/en/stable/deployment/nginx.html#build-nginx-container){:target="_blank"}).

2. Create `nginx.conf`

```conf
worker_processes 1;

events {
    worker_connections 1024;
}

http {
    upstream backend {
        least_conn;
        server vllm0:8000 max_fails=3 fail_timeout=10000s;
        server vllm1:8000 max_fails=3 fail_timeout=10000s;
        server vllm2:8000 max_fails=3 fail_timeout=10000s;
        server vllm3:8000 max_fails=3 fail_timeout=10000s;
        server vllm4:8000 max_fails=3 fail_timeout=10000s;
        server vllm5:8000 max_fails=3 fail_timeout=10000s;
        server vllm6:8000 max_fails=3 fail_timeout=10000s;
        server vllm7:8000 max_fails=3 fail_timeout=10000s;
    }

    server {
        listen 80;

        location / {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

3. Create the Docker network

```shell
docker network create vllm_nginx
```

4. Launch 8 vLLM server instances

```shell
docker run -itd \
  --ipc host \
  --network vllm_nginx \
  --device=/dev/kfd \
  --device=/dev/dri/renderD128 \
  --group-add video \
  -v $hf_cache_dir:/root/.cache/huggingface/ \
  -e HUGGING_FACE_HUB_TOKEN=$HF_TOKEN \
  -p 8081:8000 \
  --name vllm0 \
  rocm/vllm:latest \
  vllm serve meta-llama/Llama-3.1-8B-Instruct \
    --trust-remote-code \
    --max-model-len 4096
```

Above command shows for `partition-0`, which is device `/dev/dri/renderD128`. For other partitions use `renderD129` to `renderD135` and `–name` `vllm1` to `vllm7`.

5. Launch Nginx
6. From the host machine download sharegpt dataset and run vLLM benchmarks

```shell
wget \
"https://huggingface.co/datasets/anon8231489123/ShareGPT_Vicuna_unfiltered/resolve/main/ShareGPT_V3_unfiltered_cleaned_split.json"

python3 benchmark_serving.py \
   --backend vllm \
--model meta-llama/Llama-3.1-8B-Instruct \
--dataset-name sharegpt --dataset-path="ShareGPT_V3_unfiltered_cleaned_split.json" \
--request-rate=$QPS

```

The `QPS` values are `2`, `4`, .., `32`.

To run the vLLM benchmark on default mode we used a single GPU with below vLLM launch command on baremetal.

```shell
vllm serve meta-llama/Llama-3.1-8B-Instruct --max-model-len 4096
```

**Pytorch tensor parallel**

For partitioned mode we used the following steps:

1. Clone the benchmark repo

```shell
git clone https://github.com/dstackai/benchmarks.git
```

2. Run the inference benchmark

```shell
cd benchmarks
git checkout amd_partitions_benchmark
HIP_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 python3 toy_inference_benchmark.py \
       --batch-size $BATCH_SIZE

```

The `BATCH_SIZE` values are `128`, `256`, .., `32768`.

For default mode we used single MI300X with below command:

```shell
HIP_VISIBLE_DEVICES=0 python3 toy_inference_benchmark.py \
       --batch-size $BATCH_SIZE
```

## Source code

All source code and findings are available in [our GitHub repo :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/benchmarks/tree/main/amd/baremetal_container_partition){:target="_blank"}.

## References

* [AMD Instinct MI300X GPU partitioning overview :material-arrow-top-right-thin:{ .external }](https://instinct.docs.amd.com/projects/amdgpu-docs/en/latest/gpu-partitioning/mi300x/overview.html){:target="_blank"}
* [Deep dive into partition modes by AMD :material-arrow-top-right-thin:{ .external }](https://rocm.blogs.amd.com/software-tools-optimization/compute-memory-modes/README.html){:target="_blank"}.
* [RCCL and PerfTest for cluster validation by Dell :material-arrow-top-right-thin:{ .external }](https://infohub.delltechnologies.com/en-us/l/generative-ai-in-the-enterprise-with-amd-accelerators/rccl-and-perftest-for-cluster-validation-1/4/){:target="_blank"}.

## What's next?

Benchmark the performance impact of VMs vs bare-metal for inference and training, to quantify virtualization overhead.

## Acknowledgments

#### Hot Aisle
    
Big thanks to [Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"} for providing the compute power behind these benchmarks. 
If you’re looking for fast AMD GPU bare-metal or VM instances, they’re definitely worth checking out.
