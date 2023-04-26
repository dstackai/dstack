import unittest
from argparse import Namespace
from typing import List, Optional
from unittest import mock

from dstack.core.repo import RemoteRepo
from dstack.providers.docker.main import DockerProvider


def create_provider_data(
    commands: Optional[List[str]] = None, entrypoint: Optional[str] = None
) -> dict:
    return {"image": "ubuntu:20.04", "commands": commands, "entrypoint": entrypoint}


args = Namespace(args=[], unknown=[], detach=True)


class TestEntrypoint(unittest.TestCase):
    def setUp(self) -> None:
        self.hub_client = mock.Mock()
        self.hub_client.configure_mock(
            repo=RemoteRepo(repo_url="https://github.com/dstackai/dstack-playground.git")
        )

    def test_no_commands(self):
        provider = DockerProvider()
        provider.load(
            self.hub_client, args, "dummy-workflow", create_provider_data(), "dummy-run-1"
        )
        for job in provider.submit_jobs(self.hub_client, ""):
            data = job.serialize()
            self.assertListEqual(data["commands"], [])
            self.assertEqual(data["entrypoint"], None)

    def test_no_entrypoint(self):
        commands = ["echo 123", "whoami"]
        provider = DockerProvider()
        provider.load(
            self.hub_client,
            args,
            "dummy-workflow",
            create_provider_data(commands=commands),
            "dummy-run-1",
        )
        for job in provider.submit_jobs(self.hub_client, ""):
            data = job.serialize()
            self.assertListEqual(data["commands"], commands)
            self.assertListEqual(data["entrypoint"], ["/bin/sh", "-i", "-c"])

    def test_only_entrypoint(self):
        provider = DockerProvider()
        provider.load(
            self.hub_client,
            args,
            "dummy-workflow",
            create_provider_data(entrypoint="/bin/bash -ic"),
            "dummy-run-1",
        )
        for job in provider.submit_jobs(self.hub_client, ""):
            data = job.serialize()
            self.assertListEqual(data["commands"], [])
            self.assertListEqual(data["entrypoint"], ["/bin/bash", "-ic"])

    def test_entrypoint_override(self):
        commands = ["echo 123", "whoami"]
        provider = DockerProvider()
        provider.load(
            self.hub_client,
            args,
            "dummy-workflow",
            create_provider_data(commands=commands, entrypoint="/bin/bash -ic"),
            "dummy-run-1",
        )
        for job in provider.submit_jobs(self.hub_client, ""):
            data = job.serialize()
            self.assertListEqual(data["commands"], commands)
            self.assertListEqual(data["entrypoint"], ["/bin/bash", "-ic"])
