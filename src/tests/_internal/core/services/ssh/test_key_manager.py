import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from dstack._internal.core.models.users import (
    GlobalRole,
    User,
    UserPermissions,
    UserTokenCreds,
    UserWithCreds,
)
from dstack._internal.core.services.ssh.key_manager import (
    KEY_REFRESH_RATE,
    UserSSHKeyManager,
)

SAMPLE_USER = UserWithCreds(
    id=uuid.uuid4(),
    username="test",
    created_at=datetime.now(),
    global_role=GlobalRole.USER,
    active=True,
    email="test@example.com",
    permissions=UserPermissions(can_create_projects=False),
    creds=UserTokenCreds(token="7f92121b-a1b9-4ff2-8c0e-39070ffcd964"),
    ssh_public_key="ssh-rsa AAA.public",
    ssh_private_key="-----BEGIN PRIVATE KEY-----\nPRIVATE\n-----END PRIVATE KEY-----",
)
SAMPLE_USER_TOKEN_HASH = "4f010545"  # sha1(SAMPLE_USER.creds.token.encode()).hexdigest[:8]


def make_api_client(user: User, token_hash: str):
    api_client = Mock()
    api_client.get_token_hash.return_value = token_hash
    api_client.users = Mock()
    api_client.users.get_my_user.return_value = user
    return api_client


def set_mtime(path: Path, ts: float):
    os.utime(path, (ts, ts))


def test_get_user_key_downloads_keys(tmp_path: Path):
    api_client = make_api_client(user=SAMPLE_USER, token_hash=SAMPLE_USER_TOKEN_HASH)
    manager = UserSSHKeyManager(api_client, tmp_path)

    key = manager.get_user_key()
    assert key is not None
    assert key.public_key == SAMPLE_USER.ssh_public_key
    assert key.private_key_path == tmp_path / SAMPLE_USER_TOKEN_HASH
    assert (tmp_path / SAMPLE_USER_TOKEN_HASH).read_text() == SAMPLE_USER.ssh_private_key
    assert (tmp_path / f"{SAMPLE_USER_TOKEN_HASH}.pub").read_text() == SAMPLE_USER.ssh_public_key


def test_get_user_key_uses_existing_key(tmp_path: Path):
    api_client = make_api_client(user=SAMPLE_USER, token_hash=SAMPLE_USER_TOKEN_HASH)
    (tmp_path / SAMPLE_USER_TOKEN_HASH).write_text("private-contents")
    (tmp_path / f"{SAMPLE_USER_TOKEN_HASH}.pub").write_text("public-contents")

    manager = UserSSHKeyManager(api_client, tmp_path)
    key = manager.get_user_key()

    assert api_client.users.get_my_user.call_count == 0
    assert key is not None
    assert key.public_key == "public-contents"
    assert key.private_key_path == (tmp_path / SAMPLE_USER_TOKEN_HASH)


def test_get_user_key_redownloads_expired_key(tmp_path: Path):
    api_client = make_api_client(user=SAMPLE_USER, token_hash=SAMPLE_USER_TOKEN_HASH)
    priv = tmp_path / SAMPLE_USER_TOKEN_HASH
    pub = tmp_path / f"{SAMPLE_USER_TOKEN_HASH}.pub"
    priv.write_text("old-private")
    pub.write_text("old-public")
    stale_ts = time.time() - KEY_REFRESH_RATE.total_seconds() - 10
    set_mtime(priv, stale_ts)
    set_mtime(pub, stale_ts)

    manager = UserSSHKeyManager(api_client, tmp_path)
    key = manager.get_user_key()
    assert key is not None
    assert key.public_key == SAMPLE_USER.ssh_public_key
    assert key.private_key_path == priv
    assert priv.read_text() == SAMPLE_USER.ssh_private_key
    assert pub.read_text() == SAMPLE_USER.ssh_public_key
