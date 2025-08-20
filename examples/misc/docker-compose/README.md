# Docker Compose

All backends except `runpod`, `vastai`, and `kubernetes` allow using [Docker and Docker Compose](https://dstack.ai/docs/guides/protips#docker-and-docker-compose) inside `dstack` runs.

This example shows how to deploy Hugging Face [Chat UI :material-arrow-top-right-thin:{ .external }](https://huggingface.co/docs/chat-ui/index){:target="_blank"}
with [TGI :material-arrow-top-right-thin:{ .external }](https://huggingface.co/docs/text-generation-inference/en/index){:target="_blank"}
serving [Llama-3.2-3B-Instruct :material-arrow-top-right-thin:{ .external }](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct){:target="_blank"}
using [Docker Compose :material-arrow-top-right-thin:{ .external }](https://docs.docker.com/compose/){:target="_blank"}.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo with examples.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    ```
 
    </div>

## Deployment

### Running as a task

=== "`task.dstack.yml`"

    <div editor-title="examples/misc/docker-compose/task.dstack.yml">

    ```yaml
    type: task
    name: chat-ui-task

    docker: true
    env:
      - MODEL_ID=meta-llama/Llama-3.2-3B-Instruct
      - HF_TOKEN
    files:
      - compose.yaml
    commands:
      - docker compose up
    ports:
      - 9000

    resources:
      gpu: "nvidia:24GB"
    ```

    </div>

=== "`compose.yaml`"

    <div editor-title="examples/misc/docker-compose/compose.yaml">

    ```yaml
    services:
      app:
        image: ghcr.io/huggingface/chat-ui:sha-bf0bc92
        command:
          - bash
          - -c
          - |
            echo MONGODB_URL=mongodb://db:27017 > .env.local
            echo MODELS='`[{
              "name": "${MODEL_ID?}",
              "endpoints": [{"type": "tgi", "url": "http://tgi:8000"}]
            }]`' >> .env.local
            exec ./entrypoint.sh
        ports:
          - 127.0.0.1:9000:3000
        depends_on:
          - tgi
          - db

      tgi:
        image: ghcr.io/huggingface/text-generation-inference:sha-704a58c
        volumes:
          - tgi_data:/data
        environment:
          HF_TOKEN: ${HF_TOKEN?}
          MODEL_ID: ${MODEL_ID?}
          PORT: 8000
        deploy:
          resources:
            reservations:
              devices:
                - driver: nvidia
                  count: all
                  capabilities: [gpu]

      db:
        image: mongo:latest
        volumes:
          - db_data:/data/db

    volumes:
      tgi_data:
      db_data:
    ```

    </div>

### Deploying as a service

If you'd like to deploy Chat UI as an auto-scalable and secure endpoint,
use the service configuration. You can find it at [`examples/misc/docker-compose/service.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/misc/docker-compose/service.dstack.yml)

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f examples/examples/misc/docker-compose/task.dstack.yml

 #  BACKEND  REGION    RESOURCES                    SPOT  PRICE
 1  runpod   CA-MTL-1  18xCPU, 100GB, A5000:24GB    yes   $0.12
 2  runpod   EU-SE-1   18xCPU, 100GB, A5000:24GB    yes   $0.12
 3  gcp      us-west4  27xCPU, 150GB, A5000:24GB:2  yes   $0.23

Submit the run chat-ui-task? [y/n]: y

Provisioning...
---> 100%
```

</div>

## Persisting data

To persist data between runs, create a [volume](https://dstack.ai/docs/concepts/volumes/) and attach it to the run
configuration.

<div editor-title="examples/misc/docker-compose/task.dstack.yml">

```yaml
type: task
name: chat-ui-task

privileged: true
image: dstackai/dind
env:
  - MODEL_ID=meta-llama/Llama-3.2-3B-Instruct
  - HF_TOKEN
files:
  - compose.yaml
commands:
  - start-dockerd
  - docker compose up
ports:
  - 9000

# Uncomment to leverage spot instances
#spot_policy: auto

resources:
  # Required resources
  gpu: "nvidia:24GB"

volumes:
  - name: my-dind-volume
    path: /var/lib/docker
```

</div>

With this change, all Docker data—pulled images, containers, and crucially, volumes for database and model storage—will
be persisted.

## Source code

The source-code of this example can be found in
[`examples/misc/docker-compose` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/misc/docker-compose).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks),
   [services](https://dstack.ai/docs/services), and [protips](https://dstack.ai/docs/protips).
