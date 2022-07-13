from argparse import ArgumentParser
from typing import List

from dstack import Provider, Job, App


# TODO: Provide job.applications (incl. application name, and query)
class FastAPIProvider(Provider):
    def __init__(self):
        super().__init__(schema="schema.yaml")
        self.app = self.workflow.data["app"]
        self.before_run = self.workflow.data.get("before_run")
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.python = str(self.workflow.data.get("python") or "3.10")
        self.version = self.workflow.data.get("version")
        self.uvicorn = self.workflow.data.get("uvicorn")
        self.args = self.workflow.data.get("args")
        self.requirements = self.workflow.data.get("requirements")
        self.environment = self.workflow.data.get("environment") or {}
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.resources = self._resources()
        self.image = self._image()

    def parse_args(self):
        parser = ArgumentParser(prog="dstack run fastapi")
        self._add_base_args(parser)
        if self.run_as_provider:
            parser.add_argument("app", metavar="APP", type=str)
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


def main():
    provider = FastAPIProvider()
    provider.start()


if __name__ == '__main__':
    main()
