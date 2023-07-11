import unittest
from typing import List, Optional

from dstack._internal.configurators.task import TaskConfiguration, TaskConfigurator
from dstack._internal.core.job import Job
from dstack._internal.core.profile import Profile
from dstack._internal.core.repo import RemoteRepo


def configure_job(commands: List[str], entrypoint: Optional[str]) -> Job:
    conf = TaskConfiguration(
        image="ubuntu:20.04",
        commands=commands,
        entrypoint=entrypoint,
    )
    repo = RemoteRepo(repo_url="https://github.com/dstackai/dstack-playground.git")
    configurator = TaskConfigurator("docker", ".dstack.yaml", conf, Profile(name="default"))
    return configurator.get_jobs(repo, "run-name-1", "code.tar", "key.pub")[0]


class TestEntrypoint(unittest.TestCase):
    def test_no_commands(self):
        job = configure_job([], None)
        self.assertListEqual(job.commands, [])
        self.assertEqual(job.entrypoint, None)

    def test_no_entrypoint(self):
        commands = ["echo 123", "whoami"]
        job = configure_job(commands, None)
        self.assertListEqual(job.commands, commands)
        self.assertListEqual(job.entrypoint, ["/bin/sh", "-i", "-c"])

    def test_only_entrypoint(self):
        job = configure_job([], "/bin/bash -ic")
        self.assertListEqual(job.commands, [])
        self.assertListEqual(job.entrypoint, ["/bin/bash", "-ic"])

    def test_entrypoint_override(self):
        commands = ["echo 123", "whoami"]
        job = configure_job(commands, "/bin/bash -ic")
        self.assertListEqual(job.commands, commands)
        self.assertListEqual(job.entrypoint, ["/bin/bash", "-ic"])
