class ArtifactSpec:
    def __init__(self, artifact_path: str, mount: bool):
        self.artifact_path = artifact_path
        self.mount = mount

    def __str__(self) -> str:
        return f'ArtifactSpec(artifact_path="{self.artifact_path}", ' f"mount={self.mount})"


class ArtifactHead:
    def __init__(self, job_id: str, artifact_path: str):
        self.job_id = job_id
        self.artifact_path = artifact_path

    def __str__(self) -> str:
        return f'ArtifactHead(job_id="{self.job_id}", artifact_path="{self.artifact_path})'
