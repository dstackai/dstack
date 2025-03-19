# Prometheus metrics

If enabled, `dstack` collects and exports Prometheus metrics. Metrics are available at the `/metrics` path.

By default, metrics are disabled. To enable, set the `DSTACK_ENABLE_PROMETHEUS_METRICS` variable.

!!! info "Convention"
    *type?* denotes an optional type. If a type is optional, an empty string is a valid value.

## Instance metrics

| Metric | Type | Description | Examples |
|---|---|---|---|
| `dstack_instance_duration_seconds_total` | *counter* | Total seconds the instance is running | `1123763.22` |
| `dstack_instance_price_dollars_per_hour` | *gauge* | Instance price, USD/hour | `16.0`|
| `dstack_instance_gpu_count` | *gauge* | Instance GPU count | `4.0`, `0.0` |

| Label | Type | Examples |
|---|---|---|
| `dstack_project_name` | *string* | `main` |
| `dstack_fleet_name` | *string?* | `my-fleet` |
| `dstack_fleet_id` | *string?* | `51e837bf-fae9-4a37-ac9c-85c005606c22` |
| `dstack_instance_name` | *string* | `my-fleet-0` |
| `dstack_instance_id` | *string* | `8c28c52c-2f94-4a19-8c06-12f1dfee4dd2` |
| `dstack_instance_type` | *string?* | `g4dn.xlarge` |
| `dstack_backend` | *string?* | `aws`, `runpod` |
| `dstack_gpu` | *string?* | `T4` |

## Job metrics

| Metric | Type | Description | Examples |
|---|---|---|---|
| `dstack_job_duration_seconds_total` | *counter* | Total seconds the job is running | `520.37` |
| `dstack_job_price_dollars_per_hour` | *gauge* | Job instance price, USD/hour | `8.0`|
| `dstack_job_gpu_count` | *gauge* | Job GPU count | `2.0`, `0.0` |

| Label | Type | Examples |
|---|---|---|
| `dstack_project_name` | *string* | `main` |
| `dstack_user_name` | *string* | `alice` |
| `dstack_run_name` | *string* | `nccl-tests` |
| `dstack_run_id` | *string* | `51e837bf-fae9-4a37-ac9c-85c005606c22` |
| `dstack_job_name` | *string* | `nccl-tests-0-0` |
| `dstack_job_id` | *string* | `8c28c52c-2f94-4a19-8c06-12f1dfee4dd2` |
| `dstack_job_num` | *integer* | `0` |
| `dstack_replica_num` | *integer* | `0` |
| `dstack_run_type` | *string* | `task`, `dev-environment` |
| `dstack_backend` | *string* | `aws`, `runpod` |
| `dstack_gpu` | *string?* | `T4` |

## NVIDIA DCGM job metrics

A fixed subset of NVIDIA GPU metrics from [DCGM Exporter :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html){:target="_blank"} on supported cloud backends — AWS, Azure, GCP, OCI — and SSH fleets.

??? info "SSH fleets"
    In order for DCGM metrics to work, the following packages must be installed on the instances:

    * `datacenter-gpu-manager-4-core`
    * `datacenter-gpu-manager-4-proprietary`
    * `datacenter-gpu-manager-exporter`

Check [`dcgm/exporter.go`](https://github.com/dstackai/dstack/blob/master/runner/internal/shim/dcgm/exporter.go) for the list of metrics.

| Label | Type | Examples |
|---|---|---|
| `dstack_project_name` | *string* | `main` |
| `dstack_user_name` | *string* | `alice` |
| `dstack_run_name` | *string* | `nccl-tests` |
| `dstack_run_id` | *string* | `51e837bf-fae9-4a37-ac9c-85c005606c22` |
| `dstack_job_name` | *string* | `nccl-tests-0-0` |
| `dstack_job_id` | *string* | `8c28c52c-2f94-4a19-8c06-12f1dfee4dd2` |
| `dstack_job_num` | *integer* | `0` |
| `dstack_replica_num` | *integer* | `0` |
