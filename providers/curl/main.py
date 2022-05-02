from typing import List

from dstack import Provider, Job


class CurlProvider(Provider):
    def __init__(self):
        super().__init__(schema="providers/curl/schema.yaml")
        self.url = self.workflow.data["url"]
        self.output = self.workflow.data["output"]
        self.artifacts = self.workflow.data["artifacts"]

    def create_jobs(self) -> List[Job]:
        return [Job(
            image="python:3.9",
            commands=[
                f"curl {self.url} -o {self.output}"
            ],
            artifacts=self.artifacts
        )]


if __name__ == '__main__':
    provider = CurlProvider()
    provider.start()
