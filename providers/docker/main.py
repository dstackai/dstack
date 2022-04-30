from typing import List

from dstack import Provider, Job


class DockerProvider(Provider):
    def __init__(self):
        super().__init__(schema="providers/docker/schema.yaml")
        self.image = self.workflow.data["image"]
        self.commands = self.workflow.data.get("commands")
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.ports = self.workflow.data.get("ports")
        self.resources = self._resources()

    def create_jobs(self) -> List[Job]:
        return [Job(
            image_name=self.image,
            commands=self.commands,
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts,
            ports=self.ports
        )]


if __name__ == '__main__':
    provider = DockerProvider()
    provider.start()
