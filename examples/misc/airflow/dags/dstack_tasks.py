import os
import sys
from datetime import datetime, timedelta

from airflow.configuration import conf
from airflow.decorators import dag, task

# dstack repo files are stored in the dags folder as an example.
# Put dstack repo files in another place if appropriate.
DAGS_DIR_PATH = os.path.join(conf.get("core", "DAGS_FOLDER"))
DSTACK_REPO_PATH = f"{DAGS_DIR_PATH}/dstack-repo"

# A separate virtual environment should be created for dstack if dstack cannot be
# installed into the main Airflow environment. For example, due to incompatible dependencies.
DSTACK_VENV_PATH = "/path/to/dstack-venv"  # Change this !
DSTACK_VENV_PYTHON_BINARY_PATH = f"{DSTACK_VENV_PATH}/bin/python"


default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "start_date": datetime(2024, 11, 13),
}


@dag(
    default_args=default_args,
    schedule_interval=timedelta(days=1),
    catchup=False,
    description="Examples of running dstack via Airflow",
)
def dstack_tasks():
    @task.bash
    def dstack_cli_apply() -> str:
        """
        This task shows how to run the dstack CLI when
        dstack is installed into the main Airflow environment.
        NOT RECOMMENDED since dstack and Airflow may have conflicting dependencies.
        """
        return f"cd {DSTACK_REPO_PATH} && dstack init && dstack apply -y -f task.dstack.yml"

    @task.bash
    def dstack_cli_apply_venv() -> str:
        """
        This task shows how to run the dstack CLI when
        dstack is installed into a separate virtual environment available to Airflow.
        """
        return (
            f"source {DSTACK_VENV_PATH}/bin/activate"
            f" && cd {DSTACK_REPO_PATH}"
            " && dstack init"
            " && dstack apply -y -f task.dstack.yml"
        )

    @task.external_python(task_id="external_python", python=DSTACK_VENV_PYTHON_BINARY_PATH)
    def dstack_api_submit_venv():
        """
        This task shows how to run the dstack API when
        dstack is installed into a separate virtual environment available to Airflow.
        Note that the venv must have the `pendulum` package installed.
        """
        from dstack.api import Client, Task

        task = Task(
            name="my-airflow-task",
            commands=[
                "echo 'Running dstack task via Airflow'",
                "sleep 10",
                "echo 'Finished'",
            ],
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

    # Uncomment a task you want to run

    # dstack_cli_apply()
    # dstack_cli_apply_venv()
    dstack_api_submit_venv()


dstack_tasks()
