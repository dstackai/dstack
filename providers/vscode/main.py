from typing import List

from dstack import Provider, Job


# TODO: Provide job.applications (incl. application name, and query)
class VSCodeProvider(Provider):
    def __init__(self):
        super().__init__(schema="providers/python/schema.yaml")
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.python = str(self.workflow.data.get("python") or "3.10")
        self.version = self.workflow.data.get("version") or "1.67.2"
        self.requirements = self.workflow.data.get("requirements")
        self.environment = self.workflow.data.get("environment") or {}
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.resources = self._resources()
        self.image = self._image()

    def create_jobs(self) -> List[Job]:
        return [Job(
            image=self.image,
            commands=self._commands(),
            environment=self.environment,
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts,
            port_count=1
        )]

    def _image(self) -> str:
        cuda_is_required = self.resources and self.resources.gpu
        return f"dstackai/python:{self.python}-cuda-11.1" if cuda_is_required else f"python:{self.python}"

    def _commands(self):
        commands = [
            "mkdir -p /tmp",
            "cd /tmp",
            f"curl -L https://github.com/gitpod-io/openvscode-server/releases/download/openvscode-server-v{self.version}/openvscode-server-v{self.version}-linux-x64.tar.gz -O",
            f"tar -xzf openvscode-server-v{self.version}-linux-x64.tar.gz",
            f"cd openvscode-server-v{self.version}-linux-x64",
            "./bin/openvscode-server --install-extension ms-python.python"
        ]
        if self.requirements:
            commands.append("pip install -r " + self.requirements)
        commands.append(
            "./bin/openvscode-server --port $JOB_PORT_0 --host --host 0.0.0.0"
        )
        return commands


if __name__ == '__main__':
    provider = VSCodeProvider()
    provider.start()
