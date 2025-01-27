# Streamlit

## Service (no auth)

The following command runs `streamlit hello` as a service with disabled authentication:

```shell
dstack apply -f examples/misc/streamlit/.dstack.yml
```

See the configuration at [.dstack.yml](.dstack.yml).

## Task

The following command runs `streamlit hello` as a task:

```shell
dstack apply -f examples/misc/streamlit/task.dstack.yml
```

See the configuration at [task.dstack.yml](task.dstack.yml).

For more details, refer to [services](https://dstack.ai/docs/services) or [tasks](https://dstack.ai/docs/tasks).
