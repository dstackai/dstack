# dstack offer

Displays available offers (hardware configurations) from configured backends or from fleets you’ve already provisioned. Supports filtering and grouping.

The output shows backend, region, instance type, resources, spot availability, and pricing.

## Usage

This command accepts most of the same arguments as [`dstack apply`](apply.md).

<div class="termy">

```shell
$ dstack offer --help
#GENERATE#
```

</div>

## Examples

### Filtering offers

The `--gpu` flag accepts the same specification format as the `gpu` property in [`dev environment`](../../../concepts/dev-environments.md), [`task`](../../../concepts/tasks.md), 
[`service`](../../../concepts/services.md), and [`fleet`](../../../concepts/fleets.md) configurations.

The general format is: `<vendor>:<comma-sparated names>:<memory range>:<quantity range>`.

Each component is optional. 

Ranges can be:

* **Closed** (e.g. `24GB..80GB` or `1..8`)
* **Open** (e.g. `24GB..` or `1..`)
* **Single values** (e.g. `1` or `24GB`).

Examples:

* `--gpu nvidia` (any NVIDIA GPU)
* `--gpu nvidia:1..8` (from one to eigth NVIDIA GPUs)
* `--gpu A10,A100` (single NVIDIA A10 or A100 GPU)
* `--gpu A100:80GB` (single NVIDIA A100 with 80GB VRAM)
* `--gpu 24GB..80GB` (any GPU with 24GB to 80GB VRAM)

<!-- TODO: Mention TPU -->
<!-- TODO: For TPU: support https://github.com/dstackai/dstack/issues/2154 -->

The following example lists offers with one or more H100 GPUs:

<div class="termy">

```shell
$ dstack offer --gpu H100:1.. --max-offers 10
Getting offers...
---> 100%

 #   BACKEND     REGION     INSTANCE TYPE          RESOURCES                                     SPOT  PRICE   
 1   datacrunch  FIN-01     1H100.80S.30V          30xCPU, 120GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.19   
 2   datacrunch  FIN-02     1H100.80S.30V          30xCPU, 120GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.19   
 3   datacrunch  FIN-02     1H100.80S.32V          32xCPU, 185GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.19   
 4   datacrunch  ICE-01     1H100.80S.32V          32xCPU, 185GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.19   
 5   runpod      US-KS-2    NVIDIA H100 PCIe       16xCPU, 251GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.39   
 6   runpod      CA         NVIDIA H100 80GB HBM3  24xCPU, 251GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.69   
 7   nebius      eu-north1  gpu-h100-sxm           16xCPU, 200GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.95   
 8   runpod      AP-JP-1    NVIDIA H100 80GB HBM3  20xCPU, 251GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.99   
 9   runpod      CA-MTL-1   NVIDIA H100 80GB HBM3  28xCPU, 251GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.99   
 10  runpod      CA-MTL-2   NVIDIA H100 80GB HBM3  26xCPU, 125GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.99   
     ...                                                                                                                
 Shown 10 of 99 offers, $127.816 max
```

</div>

### Grouping offers

Use `--group-by` to aggregate offers. Accepted values: `gpu`, `backend`, `region`, and `count`.

<div class="termy">

```shell
dstack offer --gpu b200 --group-by gpu,backend,region
 Project      main
 User         admin
 Resources    cpu=2.. mem=8GB.. disk=100GB.. b200:1..
 Spot policy  auto
 Max price    -
 Reservation  -
 Group by     gpu, backend, region

 #   GPU              SPOT             $/GPU       BACKEND  REGION
 1   B200:180GB:1..8  spot, on-demand  3.59..5.99  runpod   EU-RO-1
 2   B200:180GB:1..8  spot, on-demand  3.59..5.99  runpod   US-CA-2
 3   B200:180GB:8     on-demand        4.99        lambda   us-east-1
 4   B200:180GB:8     on-demand        5.5         nebius   us-central1
```

</div>

When using `--group-by`, `gpu` must always be `included`.
The `region` value can only be used together with `backend`.

### JSON format
    
Use `--json` to output offers in the JSON format.

<div class="termy">

```shell
$ dstack offer --gpu amd --json
{
  "project": "main",
  "user": "admin",
  "resources": {
    "cpu": {
      "min": 2,
      "max": null
    },
    "memory": {
      "min": 8.0,
      "max": null
    },
    "shm_size": null,
    "gpu": {
      "vendor": "amd",
      "name": null,
      "count": {
        "min": 1,
        "max": 1
      },
      "memory": null,
      "total_memory": null,
      "compute_capability": null
    },
    "disk": {
      "size": {
        "min": 100.0,
        "max": null
      }
    }
  },
  "max_price": null,
  "spot": null,
  "reservation": null,
  "offers": [
    {
      "backend": "runpod",
      "region": "EU-RO-1",
      "instance_type": "AMD Instinct MI300X OAM",
      "resources": {
        "cpus": 24,
        "memory_mib": 289792,
        "gpus": [
          {
            "name": "MI300X",
            "memory_mib": 196608,
            "vendor": "amd"
          }
        ],
        "spot": false,
        "disk": {
          "size_mib": 102400
        },
        "description": "24xCPU, 283GB, 1xMI300X (192GB), 100.0GB (disk)"
      },
      "spot": false,
      "price": 2.49,
      "availability": "available"
    }
  ],
  "total_offers": 1
}
```

</div>
