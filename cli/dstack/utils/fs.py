import hashlib
from typing import BinaryIO


def get_sha256(fp: BinaryIO, chunk_size: int = 65536) -> str:
    sha256 = hashlib.sha256()
    fp.seek(0)
    chunk = fp.read(chunk_size)
    while len(chunk) > 0:
        sha256.update(chunk)
        chunk = fp.read(chunk_size)
    return sha256.hexdigest()
