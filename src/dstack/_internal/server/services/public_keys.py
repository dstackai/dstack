import asyncio
import base64
import hashlib
import subprocess
import uuid
from collections.abc import Iterable
from typing import Any, ClassVar, Optional

import paramiko.pkey
import sqlalchemy.exc
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import DstackError, ResourceExistsError, ServerClientError
from dstack._internal.core.models.keys import PublicKeyInfo
from dstack._internal.server.models import UserModel, UserPublicKeyModel
from dstack._internal.server.services import events
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import find_ssh_util

logger = get_logger(__name__)

supported_key_types = [
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "ssh-ed25519",
    "sk-ecdsa-sha2-nistp256@openssh.com",
    "sk-ssh-ed25519@openssh.com",
]


class PublicKeyError(DstackError):
    # The message displayed to the user, should not contain internal/sensitive info
    # Any debug info should be passed to the constructor as positional arguments
    # and accessed via debug_message()
    msg: ClassVar = "Public key error"

    def __init__(self, *args: Any, **kwargs: str) -> None:
        super().__init__(*args)
        self._kwargs = kwargs

    def __str__(self) -> str:
        return self.msg.format(**self._kwargs)

    def debug_message(self) -> str:
        return super().__str__()


class InvalidPublicKeyError(PublicKeyError):
    msg = "Invalid public key, must be in OpenSSH public key format"


class UnsupportedPublicKeyError(PublicKeyError):
    msg = "Unsupported key type: {type}"


async def list_user_public_keys(session: AsyncSession, user: UserModel) -> list[PublicKeyInfo]:
    res = await session.execute(
        select(UserPublicKeyModel)
        .where(UserPublicKeyModel.user_id == user.id)
        .order_by(UserPublicKeyModel.created_at.desc())
    )
    user_public_keys = res.scalars().all()
    return [user_public_key_model_to_public_key_info(k) for k in user_public_keys]


async def add_user_public_key(
    session: AsyncSession, user: UserModel, key: str, name: Optional[str] = None
) -> PublicKeyInfo:
    try:
        type_, blob, comment = parse_openssh_public_key(key)
        await validate_openssh_public_key(key)
    except PublicKeyError as e:
        logger.debug("User public key validation error: %s: %s", e, e.debug_message())
        raise ServerClientError(str(e))
    except (TimeoutError, OSError) as e:
        logger.warning("Failed to validate user public key: %s", e)
        raise ServerClientError("Failed to validate the key. Try later")

    if not name:
        name = comment or hashlib.md5(blob).hexdigest()
    fingerprint = get_openssh_public_key_fingerprint(blob)

    user_public_key = UserPublicKeyModel(
        user=user,
        name=name,
        type=type_,
        fingerprint=fingerprint,
        key=key,
    )
    try:
        async with session.begin_nested():
            session.add(user_public_key)
    except sqlalchemy.exc.IntegrityError:
        raise ResourceExistsError()
    events.emit(
        session,
        f"Public key added. Fingerprint: {fingerprint}",
        actor=events.UserActor.from_user(user),
        targets=[events.Target.from_model(user)],
    )
    await session.commit()

    return user_public_key_model_to_public_key_info(user_public_key)


async def delete_user_public_keys(
    session: AsyncSession, user: UserModel, ids: Iterable[uuid.UUID]
) -> None:
    res = await session.execute(
        delete(UserPublicKeyModel)
        .where(
            UserPublicKeyModel.user_id == user.id,
            UserPublicKeyModel.id.in_(ids),
        )
        .returning(UserPublicKeyModel.fingerprint)
    )
    for fingerprint in res.scalars().all():
        events.emit(
            session,
            f"Public key deleted. Fingerprint: {fingerprint}",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(user)],
        )
    await session.commit()


def parse_openssh_public_key(key: str) -> tuple[str, bytes, Optional[str]]:
    """
    Parses OpenSSH public key in disk format.

    Args:
        key: public key file contents.

    Returns:
        key type, blob in wire format, and optional comment.

    Raises:
        InvalidPublicKeyError: if the key disk format is not valid or the declared disk format
            key type does not match the actual key type in the blob.
            Note, the key blob is not checked, further validation is required.
        UnsupportedPublicKeyError: if the key type is not supported.
    """
    # OpenSSH disk (ASCII-armored) format for public keys:
    #       <key type> <base64-encoded wire format blob>[ <comment>]
    # See: section 4.1 "Public key format"
    # https://cvsweb.openbsd.org/checkout/src/usr.bin/ssh/PROTOCOL
    # e.g.,
    #   * without comment:
    #       ssh-ed25519 AAAAC3NzaC1lZ[...truncated...]
    #   * with default comment added by ssh-keygen:
    #       ssh-rsa AAAAB3NzaC1yc2EAAAADAQ[...truncated...] username@hostname
    #   * with user-provided comment:
    #       sk-ssh-ed25519@openssh.com AAAAGnN[...truncated...] my FIDO2 key

    # OpenSSH wire format for public keys:
    #       string      certificate or public key format identifier
    #       byte[n]     key/certificate data
    # See: https://datatracker.ietf.org/doc/html/rfc4253#section-6.6
    # Where string type is encoded as follows:
    # > They are stored as a uint32 containing its length (number of bytes that follow)
    # > and zero (= empty string) or more bytes that are the value of the string.
    # > Terminating null characters are not used.
    # See: https://datatracker.ietf.org/doc/html/rfc4251#section-5
    # e.g.,
    #       00 00 00 0b 73 73 68 2d 65 64 32 35 35 31 39 |....ssh-ed25519|

    # PublicBlob.from_string() ensures that:
    #   * there are at least two fields in the disk format: <key type> and <base64-encoded blob>
    #   * key type in the disk format (PublicBlob.key_type) matches key type in the wire format
    try:
        pb = paramiko.pkey.PublicBlob.from_string(key)
    except ValueError as e:
        raise InvalidPublicKeyError(str(e)) from e
    if pb.key_type not in supported_key_types:
        raise UnsupportedPublicKeyError(type=pb.key_type)
    return pb.key_type, pb.key_blob, pb.comment or None


def get_openssh_public_key_fingerprint(key_blob: bytes) -> str:
    """
    Returns OpenSSH public key fingerprint in the format used by OpenSSH.

    See `paramiko.pkey.PKey.fingerprint` for the implementation.

    Args:
        key_blob: public key blob in OpenSSH wire format.

    Returns:
        A fingerprint as an ASCII string, the same format OpenSSH uses.
    """
    sha256_digest_armored = base64.b64encode(hashlib.sha256(key_blob).digest()).decode()
    return f"SHA256:{sha256_digest_armored.rstrip('=')}"


async def validate_openssh_public_key(key: str) -> None:
    """
    Validates OpenSSH public key in disk format using `ssh-keygen`.

    Args:
        key: public key file contents.

    Raises:
        InvalidPublicKeyError: the key is not valid - `ssh-keygen` returned non-zero exit status.
        TimeoutError: validation timeout expired.
        OSerror: failed to execute `ssh-keygen` subprocess.
    """
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            _get_ssh_keygen_executable(),
            "-l",
            "-f",
            "-",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(proc.communicate(input=key.encode()), timeout=3)
    except asyncio.TimeoutError:
        if proc is not None:
            proc.kill()
        raise TimeoutError("Validation timeout expired")
    except OSError:
        if proc is not None:
            proc.kill()
        raise
    if proc.returncode != 0:
        raise InvalidPublicKeyError(output)


def user_public_key_model_to_public_key_info(
    user_public_key_model: UserPublicKeyModel,
) -> PublicKeyInfo:
    return PublicKeyInfo(
        id=user_public_key_model.id,
        added_at=user_public_key_model.created_at,
        name=user_public_key_model.name,
        type=user_public_key_model.type,
        fingerprint=user_public_key_model.fingerprint,
    )


_ssh_keygen_executable: Optional[str] = None


def _get_ssh_keygen_executable() -> str:
    global _ssh_keygen_executable
    if _ssh_keygen_executable is not None:
        return _ssh_keygen_executable
    ssh_keygen_path = find_ssh_util("ssh-keygen")
    if ssh_keygen_path is None:
        _ssh_keygen_executable = "ssh-keygen"
    else:
        _ssh_keygen_executable = str(ssh_keygen_path)
    return _ssh_keygen_executable
