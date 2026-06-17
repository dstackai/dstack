# dstack base images

Base images for `dstack` runner instances. A single multi-stage `Dockerfile`
produces all flavors; select one with `docker build --target <flavor>`:

- **base** — CUDA 12.8, Python (uv-managed), NCCL 2.26.2-1 + NCCL Tests, Open MPI.
- **devel** — `base` plus the CUDA development libraries and NVCC.
- **devel-efa** — `base` plus CUDA dev libraries, AWS EFA Installer 1.48.0
  (Libfabric + Open MPI + AWS OFI NCCL 1.19.0), and an EFA-aware NCCL 2.27.7-1
  build + NCCL Tests.

Build args: `UBUNTU_VERSION` (e.g. `24`).

Example:

```bash
docker build --target devel-efa --build-arg UBUNTU_VERSION=24 \
  -t dstackai/base:local-devel-efa-ubuntu24.04 -f base/Dockerfile .
```
