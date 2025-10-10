# Airflow

This example shows how to run the `dstack` CLI and API from Airflow pipelines.
It uses Airflow 2 and the [TaskFlow API](https://airflow.apache.org/docs/apache-airflow/stable/tutorial/taskflow.html).

## Preparing a virtual environment

`dstack` and Airflow may have conflicting dependencies, so it's recommended to install
`dstack` to a separate virtual environment available to Airflow.

Ensure the virtual environment created for `dstack` is
available to all the workers in case your Airflow runs in a distributed environment.

## Running dstack CLI

To run the `dstack` CLI from Airflow,
we can run it as regular bash commands using [BashOperator](https://airflow.apache.org/docs/apache-airflow/stable/howto/operator/bash.html).
The only special step here is that we need to activate a virtual environment before running `dstack`:

```python

DSTACK_VENV_PATH = "/path/to/dstack-venv"

@dag(...)
def pipeline(...):
    ...
    @task.bash
    def dstack_cli_apply_venv() -> str:
        return (
            f"source {DSTACK_VENV_PATH}/bin/activate"
            f" && cd {DSTACK_REPO_PATH}"
            " && dstack apply -y -f task.dstack.yml --repo ."
        )
```

## Running dstack API

To run the `dstack` API from Airflow, we can use [ExternalPythonOperator](https://airflow.apache.org/docs/apache-airflow/stable/howto/operator/python.html#externalpythonoperator). Specify a path to the Python binary inside the dstack virtual environment, and
Airflow will run the code inside that virtual environment:

```python

DSTACK_VENV_PYTHON_BINARY_PATH = f"{DSTACK_VENV_PATH}/bin/python"

@dag(...)
def pipeline(...):
    ...
    @task.external_python(task_id="external_python", python=DSTACK_VENV_PYTHON_BINARY_PATH)
    def dstack_api_submit_venv():
        from dstack.api import Client, Task

        task = Task(
            name="my-airflow-task",
            commands=[
                "echo 'Running dstack task via Airflow'",
                "sleep 10",
                "echo 'Finished'",
            ]
        )
        # Pick up config from `~/.dstack/config.yml`
        # or set explicitly from Ariflow Variables.
        client = Client.from_config()

        run = client.runs.apply_configuration(
            configuration=task,
        )
        run.attach()
        try:
            for log in run.logs():
                sys.stdout.buffer.write(log)
                sys.stdout.buffer.flush()
        except KeyboardInterrupt:
            run.stop(abort=True)
        finally:
            run.detach()
```

## Source code

The source code for this example can be found in
[`examples/misc/airflow` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/misc/airflow).
