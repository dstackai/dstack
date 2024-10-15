# dstack DinD

An [NVIDIA Docker in Docker](https://github.com/ehfd/nvidia-dind) image tailored for use with `dstack`

## Usage

```yaml
type: service

name: dind

image: dstackai/dind
privileged: true

port: 3000
auth: false

commands:
  # start docker daemon
  - start-dockerd
  # list stored images
  - docker image ls
  # run docker with nvidia gpu example (nvidia-smi)
  - docker run --rm --gpus all debian nvidia-smi
  # run docker compose example (gitea+postgres)
  - git clone --depth 1 https://github.com/docker/awesome-compose.git
  - cd awesome-compose/gitea-postgres
  - docker compose up

# preserve docker data root between runs (including volumes and image store)
volumes:
  - name: dind-volume
    path: /var/lib/docker
```
