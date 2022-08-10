from argparse import ArgumentParser
from typing import List, Optional, Dict, Any

from dstack.jobs import JobSpec
from dstack.providers import Provider


class CurlProvider(Provider):
    def __init__(self):
        super().__init__("curl")
        self.url = None
        self.output = None
        self.artifacts = None

    def load(self, provider_args: List[str], workflow_name: Optional[str], provider_data: Dict[str, Any]):
        super().load(provider_args, workflow_name, provider_data)
        self.url = self.provider_data["url"]
        self.output = self.provider_data["output"]
        self.artifacts = self.provider_data["artifacts"]

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or self.provider_name))
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
            self.provider_data["url"] = args.url
            self.provider_data["output"] = args.output
            self.provider_data["artifacts"] = args.artifact

    def create_job_specs(self) -> List[JobSpec]:
        return [JobSpec(
            image_name="python:3.10",
            commands=[
                f"curl {self.url} -o {self.output}"
            ],
            artifacts=self.artifacts
        )]


def __provider__():
    return CurlProvider()
