import shutil
import threading
from pathlib import Path
from typing import List, Optional

import git
import yaml
from cachetools import TTLCache, cached

from dstack._internal.core.models.templates import UITemplate
from dstack._internal.server import settings
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR_NAME = ".dstack/templates"
CACHE_TTL_SECONDS = 180

_repo_path: Optional[Path] = None
_templates_cache: TTLCache = TTLCache(maxsize=1, ttl=CACHE_TTL_SECONDS)
_templates_lock = threading.Lock()


async def list_templates() -> List[UITemplate]:
    """Return templates available for the UI.

    Currently returns only server-wide templates configured via DSTACK_SERVER_TEMPLATES_REPO.
    Project-specific templates will be included once implemented.
    """
    if not settings.SERVER_TEMPLATES_REPO:
        return []
    return await run_async(_list_templates_sync)


@cached(cache=_templates_cache, lock=_templates_lock)
def _list_templates_sync() -> List[UITemplate]:
    _fetch_templates_repo()
    return _parse_templates()


def _fetch_templates_repo() -> None:
    global _repo_path

    repo_dir = settings.SERVER_DATA_DIR_PATH / "templates-repo"

    if _repo_path is not None and _repo_path.exists():
        repo = git.Repo(str(_repo_path))
        repo.remotes.origin.pull()
        return

    if repo_dir.exists():
        try:
            repo = git.Repo(str(repo_dir))
            repo.remotes.origin.pull()
            _repo_path = repo_dir
            return
        except (git.InvalidGitRepositoryError, git.GitCommandError):
            logger.warning("Invalid templates repo at %s, re-cloning", repo_dir)
            shutil.rmtree(repo_dir)

    assert settings.SERVER_TEMPLATES_REPO is not None
    git.Repo.clone_from(
        settings.SERVER_TEMPLATES_REPO,
        str(repo_dir),
        depth=1,
    )
    _repo_path = repo_dir


def _parse_templates() -> List[UITemplate]:
    if _repo_path is None:
        return []

    templates_dir = _repo_path / TEMPLATES_DIR_NAME
    if not templates_dir.is_dir():
        logger.warning("Templates directory %s not found in repo", TEMPLATES_DIR_NAME)
        return []

    templates: List[UITemplate] = []
    for entry in sorted(templates_dir.iterdir()):
        if entry.suffix not in (".yml", ".yaml"):
            continue
        try:
            with open(entry) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                logger.warning("Skipping %s: not a valid YAML mapping", entry.name)
                continue
            if data.get("type") != "ui-template":
                logger.debug("Skipping %s: type is not 'ui-template'", entry.name)
                continue
            template = UITemplate.parse_obj(data)
            templates.append(template)
        except Exception:
            logger.warning("Skipping invalid template %s", entry.name, exc_info=True)
            continue

    return templates
