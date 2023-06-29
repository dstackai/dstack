import os
from pathlib import Path
from typing import Optional

from cryptography.hazmat.backends import default_backend as crypto_default_backend
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generage_rsa_key_pair(private_key_path: Path, public_key_path: Optional[Path] = None):
    if public_key_path is None:
        public_key_path = private_key_path.with_suffix(private_key_path.suffix + ".pub")

    key = rsa.generate_private_key(
        backend=crypto_default_backend(), public_exponent=65537, key_size=2048
    )

    def key_opener(path, flags):
        return os.open(path, flags, 0o600)

    with open(private_key_path, "wb", opener=key_opener) as f:
        f.write(
            key.private_bytes(
                crypto_serialization.Encoding.PEM,
                crypto_serialization.PrivateFormat.PKCS8,
                crypto_serialization.NoEncryption(),
            )
        )
    with open(public_key_path, "wb", opener=key_opener) as f:
        f.write(
            key.public_key().public_bytes(
                crypto_serialization.Encoding.OpenSSH,
                crypto_serialization.PublicFormat.OpenSSH,
            )
        )
        f.write(b" dstack\n")
