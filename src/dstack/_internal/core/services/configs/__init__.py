import json
import os.path
from pathlib import Path
from typing import Optional

import filelock
import yaml
from pydantic import ValidationError
from rich.prompt import Confirm

from dstack._internal.core.models.config import GlobalConfig, ProjectConfig, RepoConfig
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.utils.common import get_dstack_dir
from dstack._internal.utils.path import PathLike


class ConfigManager:
    config: GlobalConfig

    def __init__(self, dstack_dir: Optional[PathLike] = None):
        self.dstack_dir = Path(dstack_dir) if dstack_dir else get_dstack_dir()
        self.config_filepath = self.dstack_dir / "config.yaml"
        self.dstack_ssh_dir.mkdir(parents=True, exist_ok=True)
        self.load()

    def save(self):
        self.config_filepath.parent.mkdir(parents=True, exist_ok=True)
        with self.config_filepath.open("w") as f:
            # hack to convert enums to strings, etc.
            yaml.dump(json.loads(self.config.json()), f)

    def load(self):
        try:
            with open(self.config_filepath, "r") as f:
                config = yaml.safe_load(f)
            self.config = GlobalConfig.parse_obj(config)
        except (FileNotFoundError, ValidationError):
            self.config = GlobalConfig()

    def get_project_config(self, name: Optional[str] = None) -> Optional[ProjectConfig]:
        for project in self.config.projects:
            if name is None and project.default:
                return project
            if project.name == name:
                return project
        return None

    def configure_project(self, name: str, url: str, token: str, default: bool):
        if default:
            for project in self.config.projects:
                project.default = False
        for project in self.config.projects:
            if project.name == name:
                project.url = url
                project.token = token
                project.default = default or project.default
                return
        self.config.projects.append(
            ProjectConfig(name=name, url=url, token=token, default=default)
        )
        if len(self.config.projects) == 1:
            self.config.projects[0].default = True

    def delete_project(self, name: str):
        self.config.projects = [p for p in self.config.projects if p.name != name]

    def save_repo_config(
        self, repo_path: PathLike, repo_id: str, repo_type: RepoType, ssh_key_path: PathLike
    ):
        self.config_filepath.parent.mkdir(parents=True, exist_ok=True)
        with filelock.FileLock(str(self.config_filepath) + ".lock"):
            self.load()
            repo_path = os.path.abspath(repo_path)
            ssh_key_path = os.path.abspath(ssh_key_path)
            for repo in self.config.repos:
                if repo.path == repo_path:
                    repo.repo_id = repo_id
                    repo.repo_type = repo_type
                    repo.ssh_key_path = ssh_key_path
                    break
            else:
                self.config.repos.append(
                    RepoConfig(
                        path=repo_path,
                        repo_id=repo_id,
                        repo_type=repo_type,
                        ssh_key_path=ssh_key_path,
                    )
                )
            self.save()

    def get_repo_config(self, repo_path: PathLike) -> Optional[RepoConfig]:
        repo_path = os.path.abspath(repo_path)
        # TODO look at parent directories
        for repo in self.config.repos:
            if repo.path == repo_path:
                return repo
        return None

    @property
    def dstack_ssh_dir(self) -> Path:
        return self.dstack_dir / "ssh"

    @property
    def dstack_key_path(self) -> Path:
        return self.dstack_ssh_dir / "id_rsa"

    @property
    def dstack_ssh_config_path(self) -> Path:
        return self.dstack_ssh_dir / "config"


def create_default_project_config(project_name: str, url: str, token: str):
    config_manager = ConfigManager()
    default_project_config = config_manager.get_project_config()
    project_config = config_manager.get_project_config(name=project_name)
    default = default_project_config is None
    if project_config is None or default_project_config is None:
        config_manager.configure_project(name=project_name, url=url, token=token, default=default)
        config_manager.save()
        return
    if project_config.url != url or project_config.token != token:
        if Confirm.ask(
            f"The default project in {config_manager.dstack_dir / 'config.yaml'} is outdated. "
            f"Update it?"
        ):
            config_manager.configure_project(name=project_name, url=url, token=token, default=True)
        config_manager.save()
        return
