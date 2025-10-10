import tarfile
from pathlib import Path
from typing import BinaryIO

import ignore
import ignore.overrides

from dstack._internal.utils.hash import get_sha256
from dstack._internal.utils.path import PathLike, normalize_path


def create_file_archive(root: PathLike, fp: BinaryIO) -> str:
    """
    Packs the directory or file to a tar archive and writes it to the file-like object.

    Archives can be used to transfer file(s) (e.g., over the network) preserving
    file properties such as permissions, timestamps, etc.

    NOTE: `.gitignore` and `.dstackignore` are respected.

    Args:
        root: The absolute path to the directory or file.
        fp: The binary file-like object.

    Returns:
        The SHA-256 hash of the archive as a hex string.

    Raises:
        ValueError: If the path is not absolute.
        OSError: Underlying errors from the tarfile module
    """
    root = Path(root)
    if not root.is_absolute():
        raise ValueError(f"path must be absolute: {root}")
    walk = (
        ignore.WalkBuilder(root)
        .overrides(ignore.overrides.OverrideBuilder(root).add("!/.git/").build())
        .hidden(False)  # do not ignore files that start with a dot
        .require_git(False)  # respect git ignore rules even if not a git repo
        .add_custom_ignore_filename(".dstackignore")
        .build()
    )
    # sort paths to ensure archive reproducibility
    paths = sorted(entry.path() for entry in walk)
    with tarfile.TarFile(mode="w", fileobj=fp) as t:
        for path in paths:
            arcname = str(path.relative_to(root.parent))
            info = t.gettarinfo(path, arcname)
            if info.issym():
                # Symlinks are handled as follows: each symlink in the chain is checked, and
                # * if the target is inside the root: keep relative links as is, replace absolute
                #   links with relative ones;
                # * if the target is outside the root: replace the link with the actual file.
                target = Path(info.linkname)
                if not target.is_absolute():
                    target = path.parent / target
                target = normalize_path(target)
                try:
                    target.relative_to(root)
                except ValueError:
                    # Adding as a file
                    t.add(path.resolve(), arcname, recursive=False)
                else:
                    # Adding as a relative symlink
                    info.linkname = str(target.relative_to(path.parent, walk_up=True))
                    t.addfile(info)
            else:
                t.add(path, arcname, recursive=False)
    return get_sha256(fp)
