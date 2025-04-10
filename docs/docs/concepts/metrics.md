# Metrics

## Prometheus

To collect and export fleet and run metrics to Prometheus, enable the
`DSTACK_ENABLE_PROMETHEUS_METRICS` environment variable and configure Prometheus to fetch metrics from
`<dstack server URL>/metrics`.

??? info "NVIDIA DCGM"
    NVIDIA DCGM metrics are automatically collected for `aws`, `azure`, `gcp`, and `oci` backends, 
    as well as for [SSH fleets](../concepts/fleets.md#ssh).
    
    To ensure NVIDIA DCGM metrics are collected from SSH fleets, ensure the `datacenter-gpu-manager-4-core`,
    `datacenter-gpu-manager-4-proprietary`, and `datacenter-gpu-manager-exporter` packages are installed on the hosts.

### Fleets

Fleet metrics include metrics for each instance within a fleet. This includes information such as the instance's running
time, price, GPU name, and more.

=== "Metrics"
    | Name                                     | Type      | Description                       | Examples     |
    |------------------------------------------|-----------|-----------------------------------|--------------|
    | `dstack_instance_duration_seconds_total` | *counter* | Total instance runtime in seconds | `1123763.22` |
    | `dstack_instance_price_dollars_per_hour` | *gauge*   | Instance price, USD/hour          | `16.0`       |
    | `dstack_instance_gpu_count`              | *gauge*   | Instance GPU count                | `4.0`, `0.0` |

=== "Labels"
    | Name                   | Type      | Description   | Examples                               |
    |------------------------|-----------|:--------------|----------------------------------------|
    | `dstack_project_name`  | *string*  | Project name  | `main`                                 |
    | `dstack_fleet_name`    | *string?* | Fleet name    | `my-fleet`                             |
    | `dstack_fleet_id`      | *string?* | Fleet ID      | `51e837bf-fae9-4a37-ac9c-85c005606c22` |
    | `dstack_instance_name` | *string*  | Instance name | `my-fleet-0`                           |
    | `dstack_instance_id`   | *string*  | Instance ID   | `8c28c52c-2f94-4a19-8c06-12f1dfee4dd2` |
    | `dstack_instance_type` | *string?* | Instance type | `g4dn.xlarge`                          |
    | `dstack_backend`       | *string?* | Backend       | `aws`, `runpod`                        |
    | `dstack_gpu`           | *string?* | GPU name      | `H100`                                 |

### Runs

Run metrics include run counters for each user in each project.

=== "Metrics"
    | Name                                | Type      | Description                   | Examples |
    |-------------------------------------|-----------|-------------------------------|----------|
    | `dstack_run_count_total`            | *counter* | The total number of runs      | `537`    |
    | `dstack_run_count_terminated_total` | *counter* | The number of terminated runs | `118`    |
    | `dstack_run_count_failed_total`     | *counter* | The number of failed runs     | `27`     |
    | `dstack_run_count_done_total`       | *counter* | The number of successful runs | `218`    |

=== "Labels"

    | Name                  | Type      | Description   | Examples    |
    |-----------------------|-----------|:--------------|-------------|
    | `dstack_project_name` | *string*  | Project name  | `main`      |
    | `dstack_user_name`    | *string*  | User name     | `alice`     |

### Jobs

A run consists of one or more jobs, each mapped to an individual container.
For distributed workloads or auto-scalable services, a run spans multiple jobs.

Job metrics provide detailed insights into each job within a run, including execution time, cost, GPU model, DCGM
telemetry, and more.

=== "Metrics"

    | Name                                            | Type      | Description                                                                                | Examples       |
    |-------------------------------------------------|-----------|--------------------------------------------------------------------------------------------|----------------|
    | `dstack_job_duration_seconds_total`             | *counter* | Total job runtime in seconds                                                               | `520.37`       |
    | `dstack_job_price_dollars_per_hour`             | *gauge*   | Job instance price, USD/hour                                                               | `8.0`          |
    | `dstack_job_gpu_count`                          | *gauge*   | Job GPU count                                                                              | `2.0`, `0.0`   |
    | `dstack_job_cpu_count`                          | *gauge*   | Job CPU count                                                                              | `32.0`         |
    | `dstack_job_cpu_time_seconds_total`             | *counter* | Total CPU time consumed by the job, seconds                                                | `11.727975`    |
    | `dstack_job_memory_total_bytes`                 | *gauge*   | Total memory allocated for the job, bytes                                                  | `4009754624.0` |
    | `dstack_job_memory_usage_bytes`                 | *gauge*   | Memory used by the job (including cache), bytes                                            | `339017728.0`  |
    | `dstack_job_memory_working_set_bytes`           | *gauge*   | Memory used by the job (not including cache), bytes                                        | `147251200.0`  |
    | `DCGM_FI_DEV_GPU_UTIL`                          | *gauge*   | GPU utilization (in %)                                                                     |                |
    | `DCGM_FI_DEV_MEM_COPY_UTIL`                     | *gauge*   | Memory utilization (in %)                                                                  |                |
    | `DCGM_FI_DEV_ENC_UTIL`                          | *gauge*   | Encoder utilization (in %)                                                                 |                |
    | `DCGM_FI_DEV_DEC_UTIL`                          | *gauge*   | Decoder utilization (in %)                                                                 |                |
    | `DCGM_FI_DEV_FB_FREE`                           | *gauge*   | Framebuffer memory free (in MiB)                                                           |                |
    | `DCGM_FI_DEV_FB_USED`                           | *gauge*   | Framebuffer memory used (in MiB)                                                           |                |
    | `DCGM_FI_PROF_GR_ENGINE_ACTIVE`                 | *gauge*   | The ratio of cycles during which a graphics engine or compute engine remains active        |                |
    | `DCGM_FI_PROF_SM_ACTIVE`                        | *gauge*   | The ratio of cycles an SM has at least 1 warp assigned                                     |                |
    | `DCGM_FI_PROF_SM_OCCUPANCY`                     | *gauge*   | The ratio of number of warps resident on an SM                                             |                |
    | `DCGM_FI_PROF_PIPE_TENSOR_ACTIVE`               | *gauge*   | Ratio of cycles the tensor (HMMA) pipe is active                                           |                |
    | `DCGM_FI_PROF_PIPE_FP64_ACTIVE`                 | *gauge*   | Ratio of cycles the fp64 pipes are active                                                  |                |
    | `DCGM_FI_PROF_PIPE_FP32_ACTIVE`                 | *gauge*   | Ratio of cycles the fp32 pipes are active                                                  |                |
    | `DCGM_FI_PROF_PIPE_FP16_ACTIVE`                 | *gauge*   | Ratio of cycles the fp16 pipes are active                                                  |                |
    | `DCGM_FI_PROF_PIPE_INT_ACTIVE`                  | *gauge*   | Ratio of cycles the integer pipe is active                                                 |                |
    | `DCGM_FI_PROF_DRAM_ACTIVE`                      | *gauge*   | Ratio of cycles the device memory interface is active sending or receiving data            |                |
    | `DCGM_FI_PROF_PCIE_TX_BYTES`                    | *counter* | The number of bytes of active PCIe tx (transmit) data including both header and payload    |                |
    | `DCGM_FI_PROF_PCIE_RX_BYTES`                    | *counter* | The number of bytes of active PCIe rx (read) data including both header and payload        |                |
    | `DCGM_FI_DEV_SM_CLOCK`                          | *gauge*   | SM clock frequency (in MHz)                                                                |                |
    | `DCGM_FI_DEV_MEM_CLOCK`                         | *gauge*   | Memory clock frequency (in MHz)                                                            |                |
    | `DCGM_FI_DEV_MEMORY_TEMP`                       | *gauge*   | Memory temperature (in C)                                                                  |                |
    | `DCGM_FI_DEV_GPU_TEMP`                          | *gauge*   | GPU temperature (in C)                                                                     |                |
    | `DCGM_FI_DEV_POWER_USAGE`                       | *gauge*   | Power draw (in W)                                                                          |                |
    | `DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION`          | *counter* | Total energy consumption since boot (in mJ)                                                |                |
    | `DCGM_FI_DEV_PCIE_REPLAY_COUNTER`               | *counter* | Total number of PCIe retries                                                               |                |
    | `DCGM_FI_DEV_XID_ERRORS`                        | *gauge*   | Value of the last XID error encountered                                                    |                |
    | `DCGM_FI_DEV_POWER_VIOLATION`                   | *counter* | Throttling duration due to power constraints (in us)                                       |                |
    | `DCGM_FI_DEV_THERMAL_VIOLATION`                 | *counter* | Throttling duration due to thermal constraints (in us)                                     |                |
    | `DCGM_FI_DEV_SYNC_BOOST_VIOLATION`              | *counter* | Throttling duration due to sync-boost constraints (in us)                                  |                |
    | `DCGM_FI_DEV_BOARD_LIMIT_VIOLATION`             | *counter* | Throttling duration due to board limit constraints (in us)                                 |                |
    | `DCGM_FI_DEV_LOW_UTIL_VIOLATION`                | *counter* | Throttling duration due to low utilization (in us)                                         |                |
    | `DCGM_FI_DEV_RELIABILITY_VIOLATION`             | *counter* | Throttling duration due to reliability constraints (in us)                                 |                |
    | `DCGM_FI_DEV_ECC_SBE_VOL_TOTAL`                 | *counter* | Total number of single-bit volatile ECC errors                                             |                |
    | `DCGM_FI_DEV_ECC_DBE_VOL_TOTAL`                 | *counter* | Total number of double-bit volatile ECC errors                                             |                |
    | `DCGM_FI_DEV_ECC_SBE_AGG_TOTAL`                 | *counter* | Total number of single-bit persistent ECC errors                                           |                |
    | `DCGM_FI_DEV_ECC_DBE_AGG_TOTAL`                 | *counter* | Total number of double-bit persistent ECC errors                                           |                |
    | `DCGM_FI_DEV_RETIRED_SBE`                       | *counter* | Total number of retired pages due to single-bit errors                                     |                |
    | `DCGM_FI_DEV_RETIRED_DBE`                       | *counter* | Total number of retired pages due to double-bit errors                                     |                |
    | `DCGM_FI_DEV_RETIRED_PENDING`                   | *counter* | Total number of pages pending retirement                                                   |                |
    | `DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS`       | *counter* | Number of remapped rows for uncorrectable errors                                           |                |
    | `DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS`         | *counter* | Number of remapped rows for correctable errors                                             |                |
    | `DCGM_FI_DEV_ROW_REMAP_FAILURE`                 | *gauge*   | Whether remapping of rows has failed                                                       |                |
    | `DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL` | *counter* | Total number of NVLink flow-control CRC errors                                             |                |
    | `DCGM_FI_DEV_NVLINK_CRC_DATA_ERROR_COUNT_TOTAL` | *counter* | Total number of NVLink data CRC errors                                                     |                |
    | `DCGM_FI_DEV_NVLINK_REPLAY_ERROR_COUNT_TOTAL`   | *counter* | Total number of NVLink retries                                                             |                |
    | `DCGM_FI_DEV_NVLINK_RECOVERY_ERROR_COUNT_TOTAL` | *counter* | Total number of NVLink recovery errors                                                     |                |
    | `DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL`            | *counter* | Total number of NVLink bandwidth counters for all lanes                                    |                |
    | `DCGM_FI_DEV_NVLINK_BANDWIDTH_L0`               | *counter* | The number of bytes of active NVLink rx or tx data including both header and payload       |                |
    | `DCGM_FI_PROF_NVLINK_RX_BYTES`                  | *counter* | The number of bytes of active PCIe rx (read) data including both header and payload        |                |
    | `DCGM_FI_PROF_NVLINK_TX_BYTES`                  | *counter* | The number of bytes of active NvLink tx (transmit) data including both header and payload  |                |

=== "Labels"
    | Label                 | Type      | Description            | Examples                               |
    |-----------------------|-----------|:-----------------------|----------------------------------------|
    | `dstack_project_name` | *string*  | Project name           | `main`                                 |
    | `dstack_user_name`    | *string*  | User name              | `alice`                                |
    | `dstack_run_name`     | *string*  | Run name               | `nccl-tests`                           |
    | `dstack_run_id`       | *string*  | Run ID                 | `51e837bf-fae9-4a37-ac9c-85c005606c22` |
    | `dstack_job_name`     | *string*  | Job name               | `nccl-tests-0-0`                       |
    | `dstack_job_id`       | *string*  | Job ID                 | `8c28c52c-2f94-4a19-8c06-12f1dfee4dd2` |
    | `dstack_job_num`      | *integer* | Job number             | `0`                                    |
    | `dstack_replica_num`  | *integer* | Replica number         | `0`                                    |
    | `dstack_run_type`     | *string*  | Run configuration type | `task`, `dev-environment`              |
    | `dstack_backend`      | *string*  | Backend                | `aws`, `runpod`                        |
    | `dstack_gpu`          | *string?* | GPU name               | `H100`                                 |
