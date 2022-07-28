from argparse import ArgumentParser
from typing import List, Optional

from dstack import Provider, Job, App


# TODO: Provide job.applications (incl. application name, and query)
class FastAPIProvider(Provider):
    def __init__(self):
        super().__init__()
        self.app = None
        self.before_run = None
        self.python = None
        self.version = None
        self.uvicorn = None
        self.args = None
        self.requirements = None
        self.environment = None
        self.artifacts = None
        self.working_dir = None
        self.resources = None
        self.image = None

    def load(self):
        super()._load(schema="schema.yaml")
        self.app = self.workflow.data["app"]
        self.before_run = self.workflow.data.get("before_run")
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.python = self._save_python_version("python")
        self.version = self.workflow.data.get("version")
        self.uvicorn = self.workflow.data.get("uvicorn")
        self.args = self.workflow.data.get("args")
        self.requirements = self.workflow.data.get("requirements")
        self.environment = self.workflow.data.get("environment") or {}
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.resources = self._resources()
        self.image = self._image()

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or "fastapi"))
        self._add_base_args(parser)
        if not workflow_name:
            parser.add_argument("app", metavar="APP", type=str)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args = parser.parse_args(self.provider_args)
        self._parse_base_args(args)
        if self.run_as_provider:
            self.workflow.data["app"] = args.app

    def create_jobs(self) -> List[Job]:
        return [Job(
            image=self.image,
            commands=self._commands(),
            environment=self.environment,
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts,
            port_count=1,
            apps=[App(
                port_index=0,
                app_name="fastapi",
                url_path="docs",
            )]
        )]

    def _image(self) -> str:
        cuda_is_required = self.resources and self.resources.gpu
        return f"dstackai/python:{self.python}-cuda-11.1" if cuda_is_required else f"python:{self.python}"

    def _commands(self):
        commands = [
            "pip install fastapi" + (f"=={self.version}" if self.version else ""),
            "pip install \"uvicorn[standard]\"" + (f"=={self.uvicorn}" if self.uvicorn else ""),
        ]
        if self.before_run:
            commands.extend(self.before_run)
        commands.append(f"uvicorn --port $JOB_PORT_0 --host $JOB_HOSTNAME {self.app}")
        return commands


def __provider__():
    return FastAPIProvider()


if __name__ == '__main__':
    __provider__().run()
