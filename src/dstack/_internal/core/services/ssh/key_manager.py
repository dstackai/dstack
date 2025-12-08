import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from dstack._internal.core.errors import ClientError

if TYPE_CHECKING:
    from dstack.api.server import APIClient

KEY_REFRESH_RATE = timedelta(minutes=10)  # redownload the key periodically in case it was rotated


@dataclass
class UserSSHKey:
    public_key: str
    private_key_path: Path


class UserSSHKeyManager:
    def __init__(self, api_client: "APIClient", ssh_keys_dir: Path) -> None:
        self._api_client = api_client
        self._key_path = ssh_keys_dir / api_client.get_token_hash()
        self._pub_key_path = self._key_path.with_suffix(".pub")

    def get_user_key(self) -> UserSSHKey:
        """
        Return the up-to-date user key
        """
        if (
            not self._key_path.exists()
            or not self._pub_key_path.exists()
            or datetime.now() - datetime.fromtimestamp(self._key_path.stat().st_mtime)
            > KEY_REFRESH_RATE
        ):
            self._download_user_key()
        return UserSSHKey(
            public_key=self._pub_key_path.read_text(), private_key_path=self._key_path
        )

    def _download_user_key(self) -> None:
        user = self._api_client.users.get_my_user()
        if user.ssh_private_key is None or user.ssh_public_key is None:
            raise ClientError("Server response does not contain user SSH key")

        def key_opener(path, flags):
            return os.open(path, flags, 0o600)

        with open(self._key_path, "w", opener=key_opener) as f:
            f.write(user.ssh_private_key)
        with open(self._pub_key_path, "w") as f:
            f.write(user.ssh_public_key)
