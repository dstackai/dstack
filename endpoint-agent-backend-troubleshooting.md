# Endpoint Agent Backend Troubleshooting

This file is for concrete issues found while testing endpoint agent deployments. Keep it
evidence-first: record exact commands, dstack events, native backend observations, and
whether the issue was reproduced independently.

## Diagnostic Workflow

Before a live development agent run on a new or suspect hardware path, run an
independent dstack/backend preflight so agent quality is not judged against unknown
capacity:

1. Check offers with the intended endpoint constraints.
2. For VM-based backends, optionally create/update the fleet separately and wait until
   capacity can be pre-provisioned or reused.
3. For container-based backends such as RunPod and Vast.ai, do not treat fleet creation
   as pre-provisioning. Use a pinned `nodes: 0..1` fleet template or direct run
   constraints, then submit a tiny detached task to force real provisioning.
4. Submit a minimal detached task on the same backend/region/instance class, such as
   `nvidia-smi`, with a short `max_duration`.
5. If this preflight fails before image pull/logs, diagnose and record it here as a
   dstack/backend issue before running or blaming the endpoint agent.

When an endpoint agent candidate is stuck or fails, collect evidence in this order.
Prefer the normal dstack control-plane path first; use native provider APIs only when
dstack says an instance exists but the instance cannot be reached or inspected through
the project SSH path.

1. Endpoint state

   ```bash
   uv run dstack endpoint get <endpoint-name> --json
   uv run dstack logs <endpoint-name> --since 10m
   ```

2. Backing run state

   ```bash
   uv run dstack run get <run-name> --json
   uv run dstack event list --within-run <run-name> --since 30m
   uv run dstack logs <run-name> --since 30m
   ```

3. Fleet and instance state

   ```bash
   uv run dstack fleet list
   uv run dstack event list --within-fleet <fleet-name> --since 30m
   ```

4. Network and SSH reachability

   Check TCP/SSH from the same host where the dstack server runs. Use the project SSH
   key that dstack used for the run. Never copy project private keys into the report.

   ```bash
   python3 - <<'PY'
   import socket, time
   host = "<host>"
   port = 22
   start = time.time()
   try:
       s = socket.create_connection((host, port), timeout=8)
       print("tcp_connect_ok", host, port, "elapsed", round(time.time() - start, 2))
       s.close()
   except Exception as e:
       print("tcp_connect_failed", type(e).__name__, str(e), "elapsed", round(time.time() - start, 2))
   PY
   ```

5. If SSH works, inspect host bootstrap logs

   Start with:

   ```bash
   ssh <user>@<host> 'sudo systemctl status dstack-shim --no-pager || true'
   ssh <user>@<host> 'sudo journalctl -u dstack-shim -n 200 --no-pager || true'
   ssh <user>@<host> 'sudo tail -n 200 /var/log/cloud-init-output.log || true'
   ssh <user>@<host> 'docker ps -a || true'
   ssh <user>@<host> 'nvidia-smi || true'
   ```

6. Native backend state, only when needed

   Use the existing backend implementation or provider API client only when dstack has
   allocated an instance but SSH/shim is unreachable, or when dstack has no hostname and
   the provider state is required to understand why. Do not print API keys or credentials.
   For CloudRift, use `RiftClient.get_instance_by_id()` and print only sanitized fields
   such as status, node mode, host address, VM readiness, and VM state.

7. Candidate policy

   If a paid candidate remains in backend provisioning with no image pull and no logs for
   several polls, stop it and try a different backend or offer. Do not let the agent sit
   in a long shell sleep loop.

## Issue Reports

### EP-BACKEND-2026-07-04-001: CloudRift VM active in provider API, but dstack run stuck before image pull

Status: Reproduced with separate minimal tasks.

Endpoint:

- Endpoint name: `qwen-endpoint-happy`
- Endpoint id: `3383f4f4-0992-4da2-b9a0-7450a2e9d7b6`
- Agent workspace: `~/.dstack/server/data/endpoint_agent_runs/3383f4f4-0992-4da2-b9a0-7450a2e9d7b6/workspace`

Candidate run:

- Run name: `qwen-endpoint-happy-serving`
- Service image: `vllm/vllm-openai:latest`
- Model: `Qwen/Qwen3-0.6B`
- Requested resources: `gpu: 24GB..:1`, `disk: 30GB..`
- Constraints: `spot_policy: on-demand`, `max_price: 0.5`

Timeline:

- `2026-07-04 15:29:11` run submitted.
- `2026-07-04 15:29:11` job created.
- `2026-07-04 15:29:11` instance `quick-duck-0` created, status `PENDING`.
- `2026-07-04 15:29:15` job moved `SUBMITTED -> PROVISIONING`.
- `2026-07-04 15:29:15` instance moved to `PROVISIONING`.
- `2026-07-04 15:29:18` run moved `SUBMITTED -> PROVISIONING`.
- No image pull progress appeared.
- No backing service logs appeared.
- `2026-07-04 15:38:14` run was manually stopped to avoid further spend.
- Final run cost reported by dstack: `$0.0592`.

Actual dstack provisioning data:

- Backend: `cloudrift`
- Region: `ap-east-tw-kn-1`
- Instance type: `rtx49-10c-kn.1`
- GPU: `RTX4090:24GB:1`
- CPU: `7`
- Memory: `48001 MiB`
- Disk: `1024 GiB`
- Price: `$0.39/hr`
- Host address reported to dstack: `211.21.50.85`
- SSH username: `riftuser`

Native CloudRift API observation:

- Instance id: `59aa1b06-77ac-11f1-9b61-937d98c38d58`
- CloudRift status: `Active`
- Node mode: `VirtualMachine`
- Host address: `211.21.50.85`
- VM `ready`: `true`
- VM state: `Running`

Network observation from the server host:

```text
tcp_connect_failed timeout timed out elapsed 8.02
```

SSH observation:

```text
ssh: connect to host 211.21.50.85 port 22: Operation timed out
```

What this rules out:

- This was not a vLLM startup error: the container never reached image pull/startup.
- This was not a model download or dependency error: there were no job logs.
- This was not an endpoint verification failure: the service never became reachable.

Working hypothesis:

CloudRift marked the VM active/ready and returned a host address, but the dstack server
host could not reach TCP/22 on that address. The failure is likely in the provider
network path, VM SSH exposure, or early bootstrap path before dstack shim/runner became
reachable.

Latest independent repro:

- Repro run: `cloudrift-rtx49-provisioning-smoke`
- Repro time: `2026-07-04 15:58:29` to `2026-07-04 16:00:53`
- Final dstack status: `terminated`, `stopped_by_user`
- Final cost reported by dstack: `$0.015`
- Instance id: `70bb964a-77b0-11f1-bc41-ab4db0e59660`
- Backend/region/instance: `cloudrift`, `ap-east-tw-kn-1`, `rtx49-10c-kn.1`
- Native state while dstack was stuck in provisioning: CloudRift `Active`,
  `node_status=Ready`, `node_mode=VirtualMachine`, VM `ready=true`,
  VM `state=Running`
- Native host fields: `host_address=211.21.50.85`,
  `internal_host_address=10.21.106.99`
- dstack provisioning data after `vm_ready=true`: `hostname=211.21.50.85`,
  `ssh_port=22`, `username=riftuser`
- TCP/22 from the dstack server host timed out repeatedly after `vm_ready=true`
- SSH could not be attempted beyond TCP connect because port `22` was unreachable
- `dstack logs cloudrift-rtx49-provisioning-smoke --since 30m` returned no workload
  logs
- `image_pull_progress` stayed `null`

Root-cause status:

- Reproduced: yes.
- dstack-side behavior diagnosed: yes.
- Provider/backend-side failing boundary: confirmed. CloudRift reported a running,
  ready VM and returned a public host address, but the dstack server host could not
  reach `host_address:22`.
- Exact provider-side cause is still one level deeper: NAT/firewall/host-address mapping
  vs guest SSH/cloud-init. Because SSH never became reachable, host-local logs could not
  be inspected from dstack.

dstack-side diagnosis:

- `CloudRiftCompute.update_provisioning_data()` treats the VM as provisioned enough to
  try SSH once CloudRift returns `virtual_machines[0].ready == true`.
- It then sets `job_provisioning_data.hostname = instance_info["host_address"]` and
  leaves `ssh_port = 22`, `username = riftuser`.
- After that, the instance check path attempts an SSH tunnel to the shim through
  `riftuser@<host_address>:22`.
- In this failure, TCP/22 to `211.21.50.85` timed out from the dstack server host, so
  dstack could not reach the shim and the run stayed in provisioning until it was
  manually stopped.
- This means the endpoint/service/agent code was not the failing layer. The failure
  happened between CloudRift reporting VM readiness and dstack being able to establish
  SSH to the returned public address.

Most likely provider-side causes to confirm on a live rerun:

1. CloudRift returned a public `host_address` before TCP/22 was actually reachable.
2. The CloudRift host address/NAT/firewall did not expose SSH for the VM.
3. Guest `sshd` or cloud-init did not complete even though CloudRift reported VM
   `ready: true`.
4. `host_address` was shared or stale and not mapped to the VM's SSH service.

Evidence for provider/network exposure being the leading hypothesis:

- Three separate CloudRift runs returned the same public host address `211.21.50.85`.
- The runs had different internal host addresses:
  `10.21.106.174`, `10.21.106.75`, and `10.21.106.99`.
- All timed out on TCP/22 from the server host.
- No image pull or job logs were emitted, so the workload never reached container
  startup.
- Native CloudRift API later showed the first two instance IDs as `Inactive`, with the
  same `host_address`; the latest repro moved to `Deactivating` immediately after stop.
  None allowed post-mortem SSH because TCP/22 never became reachable.

Ready-to-send issue summary:

```text
Title: CloudRift VM reports ready but dstack server cannot reach returned host_address:22

Three dstack runs pinned to CloudRift ap-east-tw-kn-1 / rtx49-10c-kn.1 stayed in provisioning
before image pull/logs. CloudRift API reported VM mode VirtualMachine and VM ready/running,
and dstack received host_address 211.21.50.85 with ssh_port 22 and username riftuser.
From the same host running dstack server, TCP connect to 211.21.50.85:22 timed out and SSH
to riftuser@211.21.50.85 timed out. Two separate minimal nvidia-smi task runs reproduced
the same behavior. Please check whether host_address 211.21.50.85 should expose SSH for these VMs,
whether VM ready can be true before SSH/NAT/firewall is ready, and whether this host address
mapping is stale/shared.

Affected instance ids:
- 59aa1b06-77ac-11f1-9b61-937d98c38d58
- d8d2366a-77ad-11f1-9535-cb9f4e143a57
- 70bb964a-77b0-11f1-bc41-ab4db0e59660

Observed host address: 211.21.50.85
Observed internal host addresses: 10.21.106.174, 10.21.106.75, 10.21.106.99
```

Harness findings:

- The endpoint agent used a blocking shell wait loop:

  ```bash
  until s=$(dstack run get qwen-endpoint-happy-serving --json ...); do
      echo "status=$s ...waiting"
      sleep 15
  done
  ```

- This hid intermediate reasoning until the run was externally stopped.
- The agent recorded the planned offer as RunPod A5000 `$0.27`, but the actual
  provisioned offer was CloudRift RTX4090 `$0.39`. Learned presets must use actual
  `job_provisioning_data`, not the agent's planned candidate note.

Independent reproduction:

Run a tiny non-endpoint task constrained to the same CloudRift region and instance type,
then test whether it also gets stuck before image pull.

Reproduction config:

```yaml
type: task
name: cloudrift-rtx49-provisioning-smoke

image: nvidia/cuda:12.4.1-base-ubuntu22.04
commands:
  - nvidia-smi

resources:
  gpu: 24GB..:1
  disk: 30GB..

backends: [cloudrift]
regions: [ap-east-tw-kn-1]
instance_types: [rtx49-10c-kn.1]
spot_policy: on-demand
max_price: 0.5
max_duration: 15m
```

Reproduction run:

- Run name: `cloudrift-rtx49-provisioning-smoke`
- Config file: `cloudrift-rtx49-provisioning-smoke.dstack.yml`
- Submitted: `2026-07-04 15:39:55`
- Manually stopped: `2026-07-04 15:41:28`
- Cost when stopped: `$0.0108`
- Result: Reproduced.

Reproduction dstack events:

- `2026-07-04 15:39:55` run submitted.
- `2026-07-04 15:39:55` job created.
- `2026-07-04 15:39:55` instance `quick-duck-0` created, status `PENDING`.
- `2026-07-04 15:39:58` job moved `SUBMITTED -> PROVISIONING`.
- `2026-07-04 15:39:58` instance moved to `PROVISIONING`.
- `2026-07-04 15:40:04` run moved `SUBMITTED -> PROVISIONING`.
- No image pull progress appeared.
- No task logs appeared.

Reproduction dstack provisioning data:

- Backend: `cloudrift`
- Region: `ap-east-tw-kn-1`
- Instance id: `d8d2366a-77ad-11f1-9535-cb9f4e143a57`
- Instance type: `rtx49-10c-kn.1`
- GPU: `RTX4090:24GB:1`
- Host address reported to dstack: `211.21.50.85`
- Price: `$0.39/hr`

Reproduction native CloudRift API observation:

- CloudRift status: `Active`
- Node status: `Ready`
- Node mode: `VirtualMachine`
- Host address: `211.21.50.85`
- Internal host address: `10.21.106.75`
- VM `ready`: `true`
- VM state: `Running`
- VM name: `ubuntu-jammy-server-gpu-20250904-011801-1783172397`

Reproduction network observation from the server host:

```text
tcp_connect_failed timeout timed out elapsed 8.01
```

Reproduction SSH observation:

```text
ssh: connect to host 211.21.50.85 port 22: Operation timed out
```

Reproduction criteria used:

- Reproduced if the task also stays in `provisioning` with no image pull/logs while
  CloudRift reports VM `Active`, `ready: true`, and TCP/22 times out from the server host.
- Not reproduced if the task pulls the image, runs `nvidia-smi`, and exits.
- If SSH becomes reachable, collect `dstack-shim`, cloud-init, Docker, and `nvidia-smi`
  logs before stopping/deleting the instance.

Next harness changes suggested by this incident:

- For backend provisioning waits, use short status probes and write `agent_state.json`
  after each probe.
- After several unchanged provisioning polls with no image pull/logs, inspect dstack
  events and native backend state.
- If native backend says the VM is ready but SSH/TCP is unreachable, mark candidate as a
  backend provisioning issue and try a different offer/backend.
- Add a candidate result record that distinguishes planned offer from actual
  `job_provisioning_data`.

### EP-HARNESS-2026-07-04-002: Agent recovered with RunPod but failed to return a report

Status: Reproduced during endpoint happy-path test.

Context:

- Endpoint name: `qwen-endpoint-happy`
- First candidate: CloudRift `rtx49-10c-kn.1`, stopped after stuck provisioning.
- Second candidate: RunPod A5000 in `CA-MTL-1`, `$0.27/hr`.

What happened:

- After the CloudRift candidate was externally stopped, the agent resumed.
- It grouped offers by backend and chose RunPod A5000 as the next candidate.
- It edited `service.dstack.yml` to constrain the service to RunPod.
- It submitted `qwen-endpoint-happy-serving` again.
- The new RunPod run reached `RUNNING`.
- vLLM started successfully and loaded `Qwen/Qwen3-0.6B`.
- dstack HTTP probes reached `/v1/chat/completions` and returned `200 OK`.
- The endpoint still failed because the server agent process exited before returning a
  final verification report.

RunPod actual provisioning data:

- Backend: `runpod`
- Region: `CA-MTL-1`
- Instance type: `NVIDIA RTX A5000`
- GPU: `A5000:24GB:1`
- CPU: `9`
- Memory: `51200 MiB`
- Disk: `30 GiB`
- Price: `$0.27/hr`
- Host: `69.30.85.207`
- SSH port: `22198`

Service evidence:

- `dstack run get qwen-endpoint-happy-serving --json` reported run status `running`.
- dstack probe success streak reached `5`.
- vLLM logs included:

  ```text
  Starting vLLM server on http://0.0.0.0:8000
  Application startup complete.
  127.0.0.1:44128 - "POST /v1/chat/completions HTTP/1.1" 200 OK
  ```

Direct verification over SSH:

```text
/v1/models returned model id Qwen/Qwen3-0.6B.
/v1/chat/completions returned HTTP 200 with model Qwen/Qwen3-0.6B.
```

Proxy verification issue:

- Requests through `http://127.0.0.1:3000/proxy/services/main/qwen-endpoint-happy-serving/...`
  initially returned `404 Service main/qwen-endpoint-happy-serving not found` before the
  job was marked registered.
- After `JobModel.registered` became true, the same proxy path returned `403
  Unauthenticated or unauthorized to access project main` when using the local CLI
  project token.
- Direct SSH verification proved the service itself was healthy, so the agent should not
  have failed without a final report.

Harness findings:

- The agent should not rely on only the public proxy path for final verification.
- If the proxy returns auth/registration errors but dstack probes are passing, the agent
  should verify through `dstack attach`/SSH or another dstack-supported direct path.
- The agent must always return a structured final report on terminal success or failure.
- A successful final service should save a preset using actual RunPod provisioning data,
  not planned candidate notes.

### EP-BACKEND-2026-07-04-003: RunPod A5000 offer listed, but pinned smoke task failed with no capacity

Status: Reproduced with a separate minimal task.

Context:

- Purpose: development preflight before judging endpoint agent behavior.
- Backend: `runpod`
- Region: `CA-MTL-1`
- Instance type: `NVIDIA RTX A5000`
- Price shown by offer/apply preview: `$0.27/hr`
- Fleet template: `endpoint-agent-runpod-a5000-template`
- Fleet template nodes: `0..1`

Important distinction:

- RunPod is a container-based backend and cannot be pre-provisioned. The fleet with
  `nodes: 0..1` is only a pinned template. The actual capacity test is the smoke task.

Reproduction config:

```yaml
type: task
name: endpoint-agent-runpod-a5000-smoke

image: nvidia/cuda:12.4.1-base-ubuntu22.04
commands:
  - nvidia-smi

resources:
  gpu: 24GB..:1
  disk: 30GB..

fleets: [endpoint-agent-runpod-a5000-template]
spot_policy: on-demand
max_price: 0.3
max_duration: 15m
```

Offer/apply preview:

- `dstack offer --backend runpod --gpu 24GB.. --on-demand --max-price 0.5 --region CA-MTL-1`
  still listed `NVIDIA RTX A5000` at `$0.27/hr`.
- `dstack apply` preview for the smoke task selected the same offer through the pinned
  fleet template.

Run result:

- Submitted: `2026-07-04 15:51:13`
- Run id: `6b0a14e5-270e-45bd-8fe2-1e7524a83427`
- Job submission id: `dd5ec06e-442f-4cc3-9601-e7d60ef513ac`
- Status: `failed`
- Job status message: `no offers`
- Termination reason: `failed_to_start_due_to_no_capacity`
- Cost: `$0.0`
- `job_provisioning_data`: `null`
- No image pull progress.
- No logs.

Events:

```text
[2026-07-04 15:51:13] [run endpoint-agent-runpod-a5000-smoke] Run submitted. Status: SUBMITTED
[2026-07-04 15:51:13] [job endpoint-agent-runpod-a5000-smoke-0-0] Job created on run submission. Status: SUBMITTED
[2026-07-04 15:51:13] [instance endpoint-agent-runpod-a5000-template-0, job endpoint-agent-runpod-a5000-smoke-0-0] Instance created for job. Instance status: PENDING
[2026-07-04 15:51:14] [job endpoint-agent-runpod-a5000-smoke-0-0] Job status changed SUBMITTED -> TERMINATING. Termination reason: FAILED_TO_START_DUE_TO_NO_CAPACITY
```

What this rules out:

- This was not a model, vLLM, image, or SSH issue: the run failed before provisioning data,
  image pull, or logs.
- This did not spend GPU money.

Working hypothesis:

The RunPod offer list/apply preview can show a CA-MTL-1 A5000 offer that is not actually
allocatable at submission time. For agent testing, avoid treating a listed offer as proven
capacity until a smoke task has reached provisioning/logs/running.
