# Hugging Face Chat UI

This example shows how to deploy Hugging Face [Chat UI](https://huggingface.co/docs/chat-ui/index) with [Text Generation Inference](https://huggingface.co/docs/text-generation-inference/en/index) serving [Llama-3.2-3B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) using [Docker Compose](https://docs.docker.com/compose/).

## Configuration

1. Export your Hugging Face Hub token as the `HF_TOKEN` environment variable, e.g.,

    ```shell
    export HF_TOKEN=<token>
    ```

2. (Optional) Export the `MODEL_ID` environment variable to use a different model, e.g.,

    ```shell
    export MODEL_ID=mistralai/Mistral-7B-Instruct-v0.3
    ```

**Note**: you can also pass variable values as command line arguments to `dstack apply`:

```shell
dstack apply -f service.dstack.yml -e HF_TOKEN=<token> -e MODEL_ID=mistralai/Mistral-7B-Instruct-v0.3
```

## Deployment

The following command deploys Chat UI as a service:

```shell
dstack apply -f service.dstack.yml
```

The following command deploys Chat UI as a task:

```shell
dstack apply -f task.dstack.yml
```

## Data Persistence

To preserve data between runs, create a [volume](https://dstack.ai/docs/concepts/volumes/) and add the following lines to the run configuration (`service.dstack.yml` or `task.dstack.yml`):

```yaml
volumes:
  - name: chat-ui-volume
    path: /var/lib/docker
```

With this change, all Docker data, including pulled images, created containers, and, most importantly, volumes used for database and model storages, will be persisted.
