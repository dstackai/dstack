from collections import defaultdict
from typing import List, Optional, Tuple, Union

from dstack.backend.base import Backend
from dstack.core.repo import RepoAddress
from dstack.core.tag import TagHead


def list_tag_heads_with_merged_backends(
    backends: List[Backend], repo_address: RepoAddress
) -> List[Tuple[TagHead, List[Backend]]]:
    tags = list_tag_heads(backends, repo_address)
    tag_run_name_to_tag_map = {(t.tag_name, t.run_name): t for t, _ in tags}

    tag_run_name_to_backends_map = defaultdict(list)
    for tag, backend in tags:
        tag_run_name_to_backends_map[(tag.tag_name, tag.run_name)].append(backend)

    tag_heads_with_merged_backends = []
    for tag_run_name in tag_run_name_to_tag_map:
        tag_heads_with_merged_backends.append(
            (
                tag_run_name_to_tag_map[tag_run_name],
                list(sorted(tag_run_name_to_backends_map[tag_run_name], key=lambda b: b.name)),
            )
        )
    return tag_heads_with_merged_backends


def list_tag_heads(
    backends: List[Backend], repo_address: RepoAddress
) -> List[Tuple[TagHead, Backend]]:
    tags = []
    for backend in backends:
        tags += [(t, backend) for t in backend.list_tag_heads(repo_address)]
    return list(sorted(tags, key=lambda t: -t[0].created_at))
