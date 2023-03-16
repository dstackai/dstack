import unittest
from typing import List, Optional
from unittest.mock import patch

from dstack.backend.base import Backend
from dstack.core.repo import LocalRepoData
from dstack.providers.docker.main import DockerProvider


def load_repo_data():
    return LocalRepoData(
        repo_host_name="",
        repo_user_name="",
        repo_name="",
        repo_branch="",
        repo_hash="",
        protocol="https",
    )


def create_provider_data(
    commands: Optional[List[str]] = None, entrypoint: Optional[str] = None
) -> dict:
    return {"image": "ubuntu:20.04", "commands": commands, "entrypoint": entrypoint}


@patch("dstack.providers.load_repo_data", new=load_repo_data)
class TestEntrypoint(unittest.TestCase):
    @patch.multiple(Backend, __abstractmethods__=set())
    def setUp(self) -> None:
        self.backend = Backend()

    def test_no_commands(self):
        provider = DockerProvider()
        provider.load(self.backend, [], "dummy-workflow", create_provider_data(), "dummy-run-1")
        for job in provider.submit_jobs(self.backend, ""):
            data = job.serialize()
            self.assertListEqual(data["commands"], [])
            self.assertEqual(data["entrypoint"], None)

    def test_no_entrypoint(self):
        commands = ["echo 123", "whoami"]
        provider = DockerProvider()
        provider.load(
            self.backend,
            [],
            "dummy-workflow",
            create_provider_data(commands=commands),
            "dummy-run-1",
        )
        for job in provider.submit_jobs(self.backend, ""):
            data = job.serialize()
            self.assertListEqual(data["commands"], commands)
            self.assertListEqual(data["entrypoint"], ["/bin/sh", "-i", "-c"])

    def test_only_entrypoint(self):
        provider = DockerProvider()
        provider.load(
            self.backend,
            [],
            "dummy-workflow",
            create_provider_data(entrypoint="/bin/bash -ic"),
            "dummy-run-1",
        )
        for job in provider.submit_jobs(self.backend, ""):
            data = job.serialize()
            self.assertListEqual(data["commands"], [])
            self.assertListEqual(data["entrypoint"], ["/bin/bash", "-ic"])

    def test_entrypoint_override(self):
        commands = ["echo 123", "whoami"]
        provider = DockerProvider()
        provider.load(
            self.backend,
            [],
            "dummy-workflow",
            create_provider_data(commands=commands, entrypoint="/bin/bash -ic"),
            "dummy-run-1",
        )
        for job in provider.submit_jobs(self.backend, ""):
            data = job.serialize()
            self.assertListEqual(data["commands"], commands)
            self.assertListEqual(data["entrypoint"], ["/bin/bash", "-ic"])
