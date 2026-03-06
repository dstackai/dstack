import shutil
import threading
import uuid
from pathlib import Path
from typing import List, Optional

import git
import yaml
from cachetools import TTLCache, cached

from dstack._internal.core.models.templates import UITemplate
from dstack._internal.server import settings
from dstack._internal.server.models import ProjectModel
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR_NAME = ".dstack/templates"
CACHE_TTL_SECONDS = 180

_templates_cache: TTLCache = TTLCache(maxsize=1024, ttl=CACHE_TTL_SECONDS)
_templates_lock = threading.Lock()


async def list_templates(project: ProjectModel) -> List[UITemplate]:
    """Return templates available for the UI."""
    repo_url = project.templates_repo or settings.SERVER_TEMPLATES_REPO
    if not repo_url:
        return []
    repo_key = _repo_key(project.id, repo_url)
    return await run_async(_list_templates_sync, repo_key, repo_url)


@cached(cache=_templates_cache, lock=_templates_lock)
def _list_templates_sync(repo_key: str, repo_url: str) -> List[UITemplate]:
    try:
        repo_path = _fetch_templates_repo(repo_key, repo_url)
    except git.GitCommandError as e:
        status = getattr(e, "status", "unknown")
        stderr = (getattr(e, "stderr", "") or "").strip().splitlines()
        reason = stderr[-1] if stderr else "git command failed"
        logger.warning(
            "Failed to fetch templates repo %s (exit_code=%s): %s", repo_url, status, reason
        )
        return []
    return _parse_templates(repo_path)


def _fetch_templates_repo(repo_key: str, repo_url: str) -> Path:
    repo_dir = settings.SERVER_DATA_DIR_PATH / "templates-repos" / repo_key
    if repo_dir.exists():
        try:
            repo = git.Repo(str(repo_dir))
            remote_url = next(repo.remote().urls, None)
            if remote_url != repo_url:
                logger.info("Templates repo URL changed for key %s, re-cloning", repo_key)
                shutil.rmtree(repo_dir)
            else:
                repo.remotes.origin.pull()
                return repo_dir
        except (git.InvalidGitRepositoryError, git.GitCommandError):
            logger.warning("Invalid templates repo at %s, re-cloning", repo_dir)
            shutil.rmtree(repo_dir)

    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    git.Repo.clone_from(
        repo_url,
        str(repo_dir),
        depth=1,
    )
    return repo_dir


def _parse_templates(repo_path: Path) -> List[UITemplate]:
    templates_dir = repo_path / TEMPLATES_DIR_NAME
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
            if data.get("type") != "template":
                logger.debug("Skipping %s: type is not 'template'", entry.name)
                continue
            template = UITemplate.parse_obj(data)
            templates.append(template)
        except Exception:
            logger.warning("Skipping invalid template %s", entry.name, exc_info=True)
            continue

    return templates


def _repo_key(project_id: uuid.UUID, repo_url: str) -> str:
    key_source = f"{project_id}:{repo_url}"
    return uuid.uuid5(uuid.NAMESPACE_URL, key_source).hex


def validate_templates_repo_access(repo_url: str) -> None:
    try:
        git.Git().ls_remote("--exit-code", repo_url, "HEAD")
    except git.GitCommandError:
        raise ValueError(f"Cannot access templates repo: {repo_url}")


def invalidate_templates_cache(project_id: uuid.UUID, *repo_urls: Optional[str]) -> None:
    unique_repo_urls = {repo_url for repo_url in repo_urls if repo_url}
    with _templates_lock:
        for repo_url in unique_repo_urls:
            _templates_cache.pop((_repo_key(project_id, repo_url), repo_url), None)
