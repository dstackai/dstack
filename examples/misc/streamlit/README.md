# Streamlit

## Service (no auth)

The following command runs `streamlit hello` as a service with disabled authentication:

```shell
dstack run . -f examples/misc/streamlit/serve.dstack.yml
```

See the configuration at [serve.dstack.yml](serve.dstack.yml).

## Task

The following command runs `streamlit hello` as a task:

```shell
dstack run . -f examples/misc/streamlit/serve-task.dstack.yml
```

See the configuration at [serve-task.dstack.yml](serve-task.dstack.yml).

For more details, refer to [services](https://dstack.ai/docs/concepts/services) or [tasks](https://dstack.ai/docs/concepts/tasks).