from typing import List
import sys

from dstack import Provider, Job


class PytorchDDPProvider(Provider):
    def __init__(self):
        super().__init__(schema="providers/torchrun/schema.yaml")
        self.script = self.workflow.data["script"]
        self.version = str(self.workflow.data.get("version") or "3.9")
        self.requirements = self.workflow.data.get("requirements")
        self.environment = self.workflow.data.get("environment") or {}
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.resources = self._resources()

    def _image(self):
        cuda_is_required = self.resources and self.resources.gpu
        return f"dstackai/python:{self.version}-cuda-11.1" if cuda_is_required else f"python:{self.version}"

    def _commands(self, node_rank):
        commands = []
        if self.requirements:
            commands.append("pip3 install -r " + self.requirements)
        nproc = ""
        if self.resources.gpu:
            nproc = f"--nproc_per_node={self.resources.gpu.count}"
        nodes = self.workflow.data["resources"].get("nodes")
        if node_rank == 0:
            commands.append(
                f"torchrun {nproc} --nnodes={nodes} --node_rank={node_rank} --master_addr $JOB_HOSTNAME --master_port $JOB_PORT_0 {self.script}"
            )
        else:
            commands.append(
                f"torchrun {nproc} --nnodes={nodes} --node_rank={node_rank} --master_addr $MASTER_JOB_HOSTNAME --master_port $MASTER_JOB_PORT_0 {self.script}"
            )
        return commands

    def create_jobs(self) -> List[Job]:
        nodes = 1
        if self.workflow.data["resources"].get("nodes"):
            if not str(self.workflow.data["resources"]["nodes"]).isnumeric():
                sys.exit("resources.nodes in workflows.yaml should be an integer")
            if int(self.workflow.data["resources"]["nodes"]) > 1:
                nodes = int(self.workflow.data["resources"]["nodes"])
        masterJob = Job(
            image=self._image(),
            commands=self._commands(0),
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts,
            environment=self.environment,
            port_count=1,
        )
        jobs = [masterJob]
        if nodes > 1:
            for i in range(nodes - 1):
                jobs.append(Job(
                    image=self._image(),
                    commands=self._commands(i+1),
                    working_dir=self.working_dir,
                    resources=self.resources,
                    environment=self.environment,
                    master=masterJob
                ))
        return jobs


if __name__ == '__main__':
    provider = PytorchDDPProvider()
    provider.start()
