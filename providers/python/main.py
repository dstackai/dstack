from typing import List

from dstack import Provider, Job


class PythonProvider(Provider):
    def __init__(self):
        super().__init__(schema="providers/python/schema.yaml")
        # Drop the deprecated `python` and `python_script` properties, and make `script` required in the schema
        self.script = self.workflow.data.get("python_script") or self.workflow.data["script"]
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.version = str(self.workflow.data.get("version") or self.workflow.data.get("python") or "3.10")
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
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts
        )]

    def _image(self) -> str:
        cuda_is_required = self.resources and self.resources.gpu
        return f"dstackai/python:{self.version}-cuda-11.6.0" if cuda_is_required else f"python:{self.version}"

    def _commands(self):
        commands = []
        if self.requirements:
            commands.append("pip install -r " + self.requirements)
        environment_init = ""
        if self.environment:
            for name in self.environment:
                escaped_value = self.environment[name].replace('"', '\\"')
                environment_init += f"{name}=\"{escaped_value}\" "
        commands.append(
            f"{environment_init}python {self.script}"
        )
        return commands


if __name__ == '__main__':
    provider = PythonProvider()
    provider.start()
