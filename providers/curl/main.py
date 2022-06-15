from argparse import ArgumentParser
from typing import List

from dstack import Provider, Job


# TODO: Merge output and artifact
class CurlProvider(Provider):
    def __init__(self):
        super().__init__(schema="providers/curl/schema.yaml")
        self.url = self.workflow.data["url"]
        self.output = self.workflow.data["output"]
        self.artifacts = self.workflow.data["artifacts"]

    def parse_args(self):
        parser = ArgumentParser(prog="dstack run curl")
        if not self.workflow.data.get("workflow_name"):
            parser.add_argument("url", metavar="URL", type=str)
        # TODO: Support other curl options, such as -O
        parser.add_argument('--artifact', action='append', nargs="?", required=True)
        parser.add_argument("-o", "--output", type=str, nargs="?", required=True)
        args, unknown = parser.parse_known_args(self.provider_args)
        args.unknown = unknown
        if not self.workflow.data.get("workflow_name"):
            self.workflow.data["url"] = args.url
            self.workflow.data["output"] = args.output
            self.workflow.data["artifacts"] = args.artifact

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
