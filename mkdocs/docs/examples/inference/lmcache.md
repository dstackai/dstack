---
title: LMCache
description: Deploying Qwen3-8B using vLLM and LMCache
---

# LMCache

This example shows how to deploy `Qwen/Qwen3-8B` using
[vLLM](https://docs.vllm.ai/en/latest/), [LMCache](https://docs.lmcache.ai/),
and `dstack`.

Each service replica runs one LMCache multiprocess server alongside vLLM. This
keeps cache transfers local to the replica and allows the two processes to share
KV cache data through CUDA IPC.

## Apply a configuration

The following service uses LMCache's in-memory L1 cache and the `fs_native`
adapter for local-disk L2 storage.

<div editor-title="service.dstack.yml">

```yaml
type: service
name: qwen3-lmcache

image: lmcache/vllm-openai:v0.5.2
shell: bash

env:
  - HF_TOKEN
  - PYTHONHASHSEED=0

commands:
  - |
    set -euo pipefail

    mkdir -p /var/lib/lmcache/l2

    lmcache server \
      --host 127.0.0.1 \
      --port 5555 \
      --http-host 127.0.0.1 \
      --http-port 8080 \
      --l1-size-gb 16 \
      --max-workers 4 \
      --eviction-policy LRU \
      --l2-adapter '{
        "type": "fs_native",
        "base_path": "/var/lib/lmcache/l2",
        "num_workers": 4,
        "use_odirect": false,
        "max_capacity_gb": 150,
        "eviction": {
          "eviction_policy": "LRU",
          "trigger_watermark": 0.9,
          "eviction_ratio": 0.1
        }
      }' &
    lmcache_pid=$!

    vllm_pid=""
    cleanup() {
      kill "$lmcache_pid" 2>/dev/null || true
      if [[ -n "$vllm_pid" ]]; then
        kill "$vllm_pid" 2>/dev/null || true
      fi
    }
    trap cleanup EXIT INT TERM

    for _ in {1..120}; do
      if curl -fsS http://127.0.0.1:8080/healthcheck >/dev/null; then
        break
      fi
      kill -0 "$lmcache_pid"
      sleep 1
    done
    curl -fsS http://127.0.0.1:8080/healthcheck >/dev/null

    vllm serve Qwen/Qwen3-8B \
      --host 0.0.0.0 \
      --port 8000 \
      --tensor-parallel-size "$DSTACK_GPUS_NUM" \
      --max-model-len 16384 \
      --no-enable-prefix-caching \
      --kv-transfer-config '{
        "kv_connector": "LMCacheMPConnector",
        "kv_connector_module_path": "lmcache.integration.vllm.lmcache_mp_connector",
        "kv_role": "kv_both",
        "kv_load_failure_policy": "recompute",
        "kv_connector_extra_config": {
          "lmcache.mp.host": "tcp://127.0.0.1",
          "lmcache.mp.port": 5555
        }
      }' &
    vllm_pid=$!

    # Terminate the replica if either process exits.
    wait -n "$lmcache_pid" "$vllm_pid"
    exit 1

port: 8000
model: Qwen/Qwen3-8B
replicas: 1

probes:
  - type: http
    url: /health
    interval: 15s

volumes:
  - instance_path: /root/.cache
    path: /root/.cache
    optional: true
  - instance_path: /mnt/lmcache
    path: /var/lib/lmcache
    optional: true

resources:
  cpu: x86:8..
  memory: 40GB..
  disk: 200GB..
  shm_size: 24GB
  gpu: nvidia:24GB
```

</div>

`PYTHONHASHSEED=0` ensures that LMCache and vLLM generate the same cache keys.
On backends that support instance volumes, the optional `/mnt/lmcache` mount
keeps L2 data on the instance across container restarts, but not if the service
moves to another instance. The L2 cache is capped at 150 GB and uses LRU
eviction so it does not consume the full instance disk. `use_odirect` is
disabled because direct I/O requires filesystem-specific alignment. The
16,384-token context limit allows the model to fit on a 24 GB GPU; increase the
GPU requirement before raising this limit.

The `v0.5.2` image is an x86-64 CUDA 13 image. If the selected instance has a
driver that does not support CUDA 13, use the `v0.5.2-cu129` image tag.

Save the configuration as `service.dstack.yml`, then use the
[`dstack apply`](../../reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ dstack apply -f service.dstack.yml
```

</div>

If no gateway is created, the service endpoint will be available at
`<dstack server URL>/proxy/services/<project name>/<run name>/`.

## Validate cache reuse

In one terminal, stream the replica logs:

<div class="termy">

```shell
$ dstack logs qwen3-lmcache
```

</div>

In another terminal, send the same request twice. The generated prompt is longer
than LMCache's default 256-token chunk size, so it can produce an aligned cache
hit.

<div class="termy">

```shell
$ export SERVICE_URL=http://127.0.0.1:3000/proxy/services/main/qwen3-lmcache
$ export DSTACK_TOKEN=&lt;user token&gt;
$ REQUEST_BODY=$(python3 - <<'PY'
import json

prefix = "LMCache reuses key-value cache blocks across language-model requests. " * 80
print(json.dumps({
    "model": "Qwen/Qwen3-8B",
    "prompt": f"{prefix}\nSummarize the preceding statement.",
    "max_tokens": 32,
    "temperature": 0,
}))
PY
)
$ for _ in 1 2; do
    curl "$SERVICE_URL/v1/completions" \
      -H "Authorization: Bearer $DSTACK_TOKEN" \
      -H "Content-Type: application/json" \
      -d "$REQUEST_BODY"
  done
```

</div>

The first request should produce `Stored` entries in the LMCache server logs.
The second should produce `Retrieved` entries for the shared prefix, confirming
that the warm request reused cached KV data. Keep `replicas: 1` for this check so
both requests reach the same local cache.

> If a [gateway](../../concepts/gateways.md) is configured, use
> `https://qwen3-lmcache.<gateway domain>/` as `SERVICE_URL`.

## What's next?

1. Read about [services](../../concepts/services.md) and
   [gateways](../../concepts/gateways.md)
2. Review the [LMCache multiprocess quickstart](https://docs.lmcache.ai/mp/quickstart.html)
   and [`fs_native` storage documentation](https://docs.lmcache.ai/mp/l2_storage/fs_native.html)
3. Browse the [vLLM](./vllm.md) example
