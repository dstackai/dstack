import hashlib
import math
import string
from typing import BinaryIO

base36chars = string.digits + string.ascii_lowercase


def get_sha256(fp: BinaryIO, chunk_size: int = 65536) -> str:
    sha256 = hashlib.sha256()
    fp.seek(0)
    chunk = fp.read(chunk_size)
    while len(chunk) > 0:
        sha256.update(chunk)
        chunk = fp.read(chunk_size)
    return sha256.hexdigest()


def base36encode(value: bytes) -> str:
    output = []
    n = len(value) * math.ceil(math.log(8) / math.log(len(base36chars)))
    value = int.from_bytes(value, "little", signed=False)
    for _ in range(n):
        value, rem = divmod(value, len(base36chars))
        output.append(base36chars[rem])
    return "".join(reversed(output))


def slugify(prefix: str, unique_key: str, hash_size: int = 8) -> str:
    full_hash = base36encode(hashlib.sha256(unique_key.encode()).digest())
    return f"{prefix}-{full_hash[:hash_size]}"
