import uuid
from typing import List

from dstack import Provider, Job, App


# TODO: Provide job.applications (incl. application name, and query)
class NotebookProvider(Provider):
    def __init__(self):
        super().__init__(schema="providers/notebook/schema.yaml")
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.python = str(self.workflow.data.get("python") or "3.10")
        self.version = self.workflow.data.get("version")
        self.requirements = self.workflow.data.get("requirements")
        self.environment = self.workflow.data.get("environment") or {}
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.resources = self._resources()
        self.image = self._image()

    def create_jobs(self) -> List[Job]:
        environment = dict(self.environment)
        token = uuid.uuid4().hex
        environment["TOKEN"] = token
        return [Job(
            image=self.image,
            commands=self._commands(),
            environment=environment,
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts,
            port_count=1,
            apps=[App(
                port_index=0,
                app_name="Jupyter",
                url_query_params={
                    "token": token
                }
            )]
        )]

    def _image(self) -> str:
        cuda_is_required = self.resources and self.resources.gpu
        return f"dstackai/python:{self.python}-cuda-11.1" if cuda_is_required else f"python:{self.python}"

    def _commands(self):
        commands = [
            "pip install jupyter" + (f"=={self.version}" if self.version else ""),
            "mkdir -p /root/.jupyter",
            "echo \"c.NotebookApp.allow_root = True\" > /root/.jupyter/jupyter_notebook_config.py",
            "echo \"c.NotebookApp.open_browser = False\" >> /root/.jupyter/jupyter_notebook_config.py",
            "echo \"c.NotebookApp.port = $JOB_PORT_0\" >> /root/.jupyter/jupyter_notebook_config.py",
            "echo \"c.NotebookApp.token = '$TOKEN'\" >> /root/.jupyter/jupyter_notebook_config.py",
            "echo \"c.NotebookApp.ip = '$JOB_HOSTNAME'\" >> /root/.jupyter/jupyter_notebook_config.py",
        ]
        if self.requirements:
            commands.append("pip install -r " + self.requirements)
        commands.append(
            f"jupyter notebook"
        )
        return commands


if __name__ == '__main__':
    provider = NotebookProvider()
    provider.start()
