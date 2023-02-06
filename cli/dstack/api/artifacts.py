from collections import defaultdict
from typing import List, Optional, Tuple, Union

from dstack.backend import Backend
from dstack.core.artifact import Artifact
from dstack.core.repo import RepoAddress


def list_artifacts_with_merged_backends(
    backends: List[Backend],
    repo_address: RepoAddress,
    run_name: str,
) -> List[Tuple[Artifact, List[Backend]]]:
    artifacts = list_artifacts(backends, repo_address, run_name)

    artifact_name_file_to_artifact_map = {(a.name, a.file): a for a, _ in artifacts}

    artifact_name_file_to_backends_map = defaultdict(list)
    for artifact, backend in artifacts:
        artifact_name_file_to_backends_map[(artifact.name, artifact.file)].append(backend)

    artifacts_with_merged_backends = []
    for artifact_name_file in artifact_name_file_to_artifact_map:
        artifacts_with_merged_backends.append(
            (
                artifact_name_file_to_artifact_map[artifact_name_file],
                artifact_name_file_to_backends_map[artifact_name_file],
            )
        )
    return artifacts_with_merged_backends


def list_artifacts(
    backends: List[Backend], repo_address: RepoAddress, run_name: str
) -> List[Tuple[Artifact, Backend]]:
    artifacts = []
    for backend in backends:
        artifacts += [
            (a, backend) for a in backend.list_run_artifact_files(repo_address, run_name)
        ]
    return artifacts
