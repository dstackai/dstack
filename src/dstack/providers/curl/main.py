from argparse import ArgumentParser
from typing import List, Optional

from dstack import Provider, Job


# TODO: Merge output and artifact
class CurlProvider(Provider):
    def __init__(self):
        super().__init__()
        self.url = None
        self.output = None
        self.artifacts = None

    def load(self):
        super()._load(schema="schema.yaml")
        self.url = self.workflow.data["url"]
        self.output = self.workflow.data["output"]
        self.artifacts = self.workflow.data["artifacts"]

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or "curl"))
        if not workflow_name:
            parser.add_argument("url", metavar="URL", type=str)
        # TODO: Support other curl options, such as -O
        parser.add_argument('-a', '--artifact', action='append', required=True)
        parser.add_argument("-o", "--output", type=str, required=True)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args, unknown = parser.parse_known_args(self.provider_args)
        args.unknown = unknown
        if self.run_as_provider:
            self.workflow.data["url"] = args.url
            self.workflow.data["output"] = args.output
            self.workflow.data["artifacts"] = args.artifact

    def create_jobs(self) -> List[Job]:
        return [Job(
            image="python:3.10",
            commands=[
                f"curl {self.url} -o {self.output}"
            ],
            artifacts=self.artifacts
        )]


def __provider__():
    return CurlProvider()


if __name__ == '__main__':
    __provider__().run()
