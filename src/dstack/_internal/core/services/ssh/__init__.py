from dstack._internal.core.errors import (
    SSHConnectionRefusedError,
    SSHError,
    SSHKeyError,
    SSHPortInUseError,
    SSHTimeoutError,
)


def get_ssh_error(stderr: bytes) -> SSHError:
    if b": Permission denied (publickey)" in stderr:
        return SSHKeyError(stderr)

    for pattern, cls in [
        (b": Operation timed out", SSHTimeoutError),
        (b": Connection refused", SSHConnectionRefusedError),
        (b": Address already in use", SSHPortInUseError),
        (b" port forwarding failed", SSHPortInUseError),
    ]:
        if pattern in stderr:
            return cls(
                b"\n".join(line for line in stderr.split(b"\n") if pattern in line).decode()
            )

    # TODO: kex_exchange_identification: read: Connection reset by peer
    # TODO: Connection timed out during banner exchange
    return SSHError(stderr.decode())
