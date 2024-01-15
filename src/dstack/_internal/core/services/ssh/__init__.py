from dstack._internal.core.errors import (
    SSHConnectionRefusedError,
    SSHError,
    SSHKeyError,
    SSHPortInUseError,
    SSHTimeoutError,
)


def get_ssh_error(stderr: bytes) -> SSHError:
    if b": Operation timed out" in stderr:
        return SSHTimeoutError()
    if b": Connection refused" in stderr:
        return SSHConnectionRefusedError()
    if b": Permission denied (publickey)" in stderr:
        return SSHKeyError(stderr)
    if b": Address already in use" in stderr:
        return SSHPortInUseError()
    # TODO: kex_exchange_identification: read: Connection reset by peer
    # TODO: Connection timed out during banner exchange
    return SSHError(stderr.decode())
