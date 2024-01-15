import os
import subprocess
import tempfile
from typing import List, Optional

from dstack._internal.core.services.ssh import get_ssh_error


def ssh_execute_command(
    host: str,
    id_rsa: str,
    command: str,
    *,
    options: Optional[List[str]] = None,
) -> str:
    id_rsa_file = tempfile.NamedTemporaryFile("w")
    id_rsa_file.write(id_rsa)
    id_rsa_file.flush()
    id_rsa_file.seek(0)
    os.chmod(id_rsa_file.name, 0o600)

    cmd = ["ssh", "-i", id_rsa_file.name]
    cmd += ["-o", "StrictHostKeyChecking=no"]
    cmd += ["-o", "UserKnownHostsFile=/dev/null"]
    cmd += options or []
    cmd += [host, command]

    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise get_ssh_error(r.stderr)
    return r.stdout.decode()
