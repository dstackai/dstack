import uuid
from argparse import ArgumentParser
from typing import List, Optional

from dstack import Job, App, JobSpec
from dstack.providers import Provider


class LabProvider(Provider):
    def __init__(self):
        super().__init__("lab")
        self.before_run = None
        self.python = None
        self.version = None
        self.requirements = None
        self.environment = None
        self.artifacts = None
        self.working_dir = None
        self.resources = None
        self.image_name = None

    def load(self):
        super()._load(schema="schema.yaml")
        self.before_run = self.workflow.data.get("before_run")
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.python = self._save_python_version("python")
        self.version = self.workflow.data.get("version")
        self.requirements = self.workflow.data.get("requirements")
        self.environment = self.workflow.data.get("environment") or {}
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.resources = self._resources()
        self.image_name = self._image()

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or self.provider_name))
        self._add_base_args(parser)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args = parser.parse_args(self.provider_args)
        self._parse_base_args(args)

    def create_job_specs(self) -> List[JobSpec]:
        env = dict(self.environment)
        token = uuid.uuid4().hex
        env["TOKEN"] = token
        return [JobSpec(
            image_name=self.image_name,
            commands=self._commands(),
            env=env,
            working_dir=self.working_dir,
            artifacts=self.artifacts,
            port_count=1,
            requirements=self.resources,
            apps=[App(
                port_index=0,
                app_name="lab",
                url_path="lab",
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
            "pip install jupyterlab" + (f"=={self.version}" if self.version else ""),
            "mkdir -p /root/.jupyter",
            "echo \"c.ServerApp.allow_root = True\" > /root/.jupyter/jupyter_server_config.py",
            "echo \"c.ServerApp.open_browser = False\" >> /root/.jupyter/jupyter_server_config.py",
            "echo \"c.ServerApp.port = $JOB_PORT_0\" >> /root/.jupyter/jupyter_server_config.py",
            "echo \"c.ServerApp.token = '$TOKEN'\" >> /root/.jupyter/jupyter_server_config.py",
            "echo \"c.ServerApp.ip = '$JOB_HOSTNAME'\" >> /root/.jupyter/jupyter_server_config.py",
        ]
        if self.requirements:
            commands.append("pip install -r " + self.requirements)
        if self.before_run:
            commands.extend(self.before_run)
        commands.append(
            f"jupyter lab"
        )
        return commands


def __provider__():
    return LabProvider()


if __name__ == '__main__':
    __provider__().run()
