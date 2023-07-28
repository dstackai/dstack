import logging
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Type, Union

import watchfiles

from dstack._internal.utils.common import PathLike
from dstack._internal.utils.ignore import GitIgnore


class FSEvent(NamedTuple):
    path: Path
    time: float


class Copier(threading.Thread):
    def __init__(
        self,
        *,
        q: queue.Queue,
        stop_event: threading.Event,
        src_root: Path,
        timeout: float = 1.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.queue = q
        self.stop_event = stop_event
        self.src_root = Path(src_root)
        self.timeout = timeout
        self.last_accessed: Dict[Path, float] = {}

    def rm(self, path: Path):
        """
        :param path: absolute path to file or dir
        :return:
        """
        raise NotImplementedError()

    def copy(self, path: Path):
        """
        :param path: absolute path to file
        :return:
        """
        raise NotImplementedError()

    def run(self):
        while not self.stop_event.is_set():
            try:
                event: FSEvent = self.queue.get(timeout=self.timeout)
            except queue.Empty:
                continue
            if event.time < self.last_accessed.get(event.path, 0):
                continue

            self.last_accessed[event.path] = time.monotonic()
            if not event.path.exists():
                self.rm(event.path)
            elif event.path.is_file():
                self.copy(event.path)


class WatcherFilter(watchfiles.DefaultFilter):
    def __init__(self, root_dir: PathLike, **kwargs):
        super().__init__(**kwargs)
        self.gitignore = GitIgnore(Path(root_dir))

    def __call__(self, change: watchfiles.Change, path: str) -> bool:
        return super().__call__(change, path) and not self.gitignore.ignore(path)


class Watcher(threading.Thread):
    def __init__(self, root_dir: PathLike, **kwargs):
        super().__init__(**kwargs)
        self.root_dir = Path(root_dir).resolve()
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.copier: Optional[Copier] = None

    def stop(self):
        self.stop_event.set()

    def run(self) -> None:
        for updates in watchfiles.watch(
            self.root_dir, stop_event=self.stop_event, watch_filter=WatcherFilter(self.root_dir)
        ):
            for _, path in updates:
                self.queue.put(FSEvent(Path(path), time.monotonic()))

    def start_copier(self, copier_cls: Type[Copier], **kwargs):
        self.copier = copier_cls(
            q=self.queue, stop_event=self.stop_event, src_root=self.root_dir, **kwargs
        )
        self.copier.start()

    def join(self, timeout: Optional[float] = None):
        super().join(timeout=timeout)
        if self.copier is not None:
            self.copier.join(timeout=timeout)


class LocalCopier(Copier):
    def __init__(self, *, dst_root: PathLike, **kwargs):
        super().__init__(**kwargs)
        self.dst_root = Path(dst_root)

    def rm(self, path: Path):
        target = self.dst_root / path.relative_to(self.src_root)
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.is_file():
            target.unlink()

    def copy(self, path: Path):
        target = self.dst_root / path.relative_to(self.src_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copy(path, target)


class SSHCopier(Copier):
    def __init__(self, *, ssh_host: str, dst_root: PathLike, **kwargs):
        super().__init__(**kwargs)
        self.dst_root = Path(dst_root)
        self.ssh_host = ssh_host

    @staticmethod
    def _exec(args: List[Union[str, PathLike]]) -> int:
        logging.debug(f"SSHCopier: {args}")
        return subprocess.run(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode

    def rm(self, path: Path):
        target = self.dst_root / path.relative_to(self.src_root)
        self._exec(["ssh", self.ssh_host, f"rm -rf {target}"])

    def copy(self, path: Path):
        target = self.dst_root / path.relative_to(self.src_root)
        self._exec(
            [
                "ssh",
                self.ssh_host,
                f'mkdir -p "{target.parent}"; if [ -d "{target}" ]; then rm -rf "{target}"; fi',
            ]
        )
        self._exec(["scp", path, f"{self.ssh_host}:{target}"])
