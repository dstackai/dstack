import uuid
from argparse import ArgumentParser
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

    def parse_args(self):
        parser = ArgumentParser(prog="dstack run notebook")
        parser.add_argument("-r", "--requirements", type=str, nargs="?")
        parser.add_argument('-e', '--env', action='append', nargs="?")
        parser.add_argument('--artifact', action='append', nargs="?")
        # TODO: Support depends-on
        parser.add_argument("--working-dir", type=str, nargs="?")
        # parser.add_argument('--depends-on', action='append', nargs="?")
        parser.add_argument("--cpu", type=int, nargs="?")
        parser.add_argument("--memory", type=str, nargs="?")
        parser.add_argument("--gpu", type=int, nargs="?")
        parser.add_argument("--gpu-name", type=str, nargs="?")
        parser.add_argument("--gpu-memory", type=str, nargs="?")
        parser.add_argument("--shm-size", type=str, nargs="?")
        args = parser.parse_args(self.provider_args)
        if args.requirements:
            self.workflow.data["requirements"] = args.requirements
        if args.artifact:
            self.workflow.data["artifacts"] = args.artifact
        if args.working_dir:
            self.workflow.data["working_dir"] = args.working_dir
        if args.env:
            environment = self.workflow.data.get("environment") or {}
            for e in args.env:
                if "=" in e:
                    tokens = e.split("=", maxsplit=1)
                    environment[tokens[0]] = tokens[1]
                else:
                    environment[e] = ""
            self.workflow.data["environment"] = environment
        if args.cpu or args.memory or args.gpu or args.gpu_name or args.gpu_memory or args.shm_size:
            resources = self.workflow.data["resources"] or {}
            self.workflow.data["resources"] = resources
            if args.cpu:
                resources["cpu"] = args.cpu
            if args.memory:
                resources["memory"] = args.memory
            if args.gpu or args.gpu_name or args.gpu_memory:
                gpu = self.workflow.data["resources"].get("gpu") or {} if self.workflow.data.get("resources") else {}
                if type(gpu) is int:
                    gpu = {
                        "count": gpu
                    }
                resources["gpu"] = gpu
                if args.gpu:
                    gpu["count"] = args.gpu
                if args.gpu_memory:
                    gpu["memory"] = args.gpu_memory
                if args.gpu_name:
                    gpu["name"] = args.gpu_name
            if args.shm_size:
                resources["shm_size"] = args.shm_size

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
