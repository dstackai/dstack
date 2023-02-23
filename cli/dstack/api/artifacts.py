from collections import defaultdict
from typing import List, Optional, Tuple, Union

from dstack.backend.base import Backend
from dstack.core.artifact import Artifact
from dstack.core.repo import RepoAddress


def list_artifacts_with_merged_backends(
    backends: List[Backend],
    repo_address: RepoAddress,
    run_name: str,
) -> List[Tuple[Artifact, List[Backend]]]:
    artifacts = list_artifacts(backends, repo_address, run_name)

    artifact_name_to_artifact_map = {a.name: a for a, _ in artifacts}

    artifact_name_to_backends_map = defaultdict(list)
    for artifact, backend in artifacts:
        artifact_name_to_backends_map[artifact.name].append(backend)

    artifacts_with_merged_backends = []
    for artifact_name in artifact_name_to_artifact_map:
        artifacts_with_merged_backends.append(
            (
                artifact_name_to_artifact_map[artifact_name],
                artifact_name_to_backends_map[artifact_name],
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
