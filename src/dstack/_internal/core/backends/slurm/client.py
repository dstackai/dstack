import dataclasses
import ipaddress
import re
import shlex
import uuid
from types import TracebackType
from typing import Optional

import paramiko
from typing_extensions import Self

from dstack._internal.core.backends.slurm.resources import Node, ResolvedNode
from dstack._internal.core.errors import ComputeError
from dstack._internal.utils.ssh import pkey_from_str

DEFAULT_TIMEOUT = 10


@dataclasses.dataclass
class ExecResult:
    exit_status: int
    stdout: bytes
    stderr: bytes

    @property
    def ok(self) -> bool:
        return self.exit_status == 0


class SlurmClientError(ComputeError):
    pass


class SlurmClient:
    _client: Optional[paramiko.SSHClient] = None

    def __init__(
        self,
        *,
        hostname: str,
        port: int,
        user: str,
        private_key: str,
        timeout: Optional[float] = None,
    ) -> None:
        self._hostname = hostname
        self._port = port
        self._user = user
        self._private_key = private_key
        self._timeout = timeout or DEFAULT_TIMEOUT

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def connect(self, *, timeout: Optional[float] = None) -> None:
        """
        Connect to the SSH server. No-op if already connected.
        """
        if self._client is not None:
            return
        try:
            pkey = pkey_from_str(self._private_key)
        except ValueError as e:
            raise SlurmClientError(f"Failed to load private key: {e}") from e
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
        try:
            self._client.connect(
                hostname=self._hostname,
                port=self._port,
                username=self._user,
                pkey=pkey,
                timeout=self._get_timeout(timeout),
            )
        except (paramiko.SSHException, OSError) as e:
            raise SlurmClientError(f"Failed to connect: {e}") from e

    def close(self) -> None:
        """
        Disconnect from the SSH server. No-op if not connected.
        """
        if self._client is None:
            return
        self._client.close()
        self._client = None

    def ping(self) -> None:
        res = self.exec("scontrol ping")
        if not res.ok:
            raise SlurmClientError(f"Failed to ping: {res}")

    def get_partitions(self) -> list[str]:
        res = self.exec("sinfo -h -o '%P'")
        if not res.ok:
            raise SlurmClientError(f"Failed to get partitions: {res}")
        return [
            part.rstrip("*") for line in res.stdout.decode().splitlines() if (part := line.strip())
        ]

    def get_nodes(self) -> list[Node]:
        res = self.exec("scontrol show -o node")
        if not res.ok:
            raise SlurmClientError(f"Failed to get nodes: {res}")
        nodes: list[Node] = []
        for node_line in filter(None, res.stdout.decode().splitlines()):
            node_dict = _parse_scontrol_show_line(node_line)
            try:
                node = _build_node_from_dict(node_dict)
            except ValueError as e:
                raise SlurmClientError(f"Failed to parse node: {e}") from e
            nodes.append(node)
        return nodes

    def submit_batch_script(self, batch_script: str) -> str:
        script = f"sbatch --parsable << 'EOF'\n{batch_script}\nEOF"
        res = self.exec(script)
        if not res.ok:
            raise SlurmClientError(f"Failed to submit batch script: {res}")
        output = res.stdout.decode().strip()
        if not output:
            raise SlurmClientError("Failed to submit batch script: sbatch output is empty")
        # > --parsable
        # > Outputs only the job ID number and the cluster name if present.
        # > The values are separated by a semicolon.
        job_id, _, _ = output.partition(";")
        job_id = job_id.strip()
        if not job_id:
            raise SlurmClientError(
                f"Failed to submit batch script: unexpected sbatch output: {output!r}"
            )
        return job_id

    def get_job_state(self, job_id: str) -> Optional[str]:
        res = self.exec(f"squeue -j {job_id} --only-job-state -h -o '%T'")
        if not res.ok:
            raise SlurmClientError(f"Failed to queue job state: {res}")
        if state := res.stdout.decode().strip():
            return state
        return None

    def get_job_partition(self, job_id: str) -> str:
        res = self.exec(f"squeue -j {job_id} -h -o '%P'")
        if not res.ok:
            raise SlurmClientError(f"Failed to queue job partition: {res}")
        return res.stdout.decode().strip()

    def get_job_nodes(self, job_id: str) -> list[ResolvedNode]:
        res = self.exec(f"""
            set -eu
            nodelist=$(squeue -j {job_id} -h -o '%N')
            scontrol show -o node="$nodelist"
        """)
        if not res.ok:
            raise SlurmClientError(f"Failed to get job nodes: {res}")

        nodes: list[ResolvedNode] = []
        nodes_to_resolve: list[tuple[Node, str]] = []
        for node_line in filter(None, res.stdout.decode().splitlines()):
            node_dict = _parse_scontrol_show_line(node_line)
            try:
                node = _build_node_from_dict(node_dict)
            except ValueError as e:
                raise SlurmClientError(f"Failed to parse node: {e}") from e

            addresses: list[str] = []
            if node_addr := node_dict.get("nodeaddr"):
                addresses.append(node_addr)
            if node_hostname := node_dict.get("nodehostname"):
                addresses.append(node_hostname)
            hostnames: list[str] = []
            ips: list[str] = []
            for address in addresses:
                try:
                    ips.append(str(ipaddress.ip_address(address)))
                except ValueError:
                    hostnames.append(address)
            hostname = next(iter(hostnames), None)
            ip = next(iter(ips), None)
            if ip is None:
                if hostname is None:
                    raise SlurmClientError(f"Failed to get hostname/IP: {node_line!r}")
                nodes_to_resolve.append((node, hostname))
            else:
                hostname = hostname or ip
                nodes.append(ResolvedNode(**dataclasses.asdict(node), hostname=hostname, ip=ip))

        if nodes_to_resolve:
            # getent prints one line per address; keep only the first so that each hostname maps
            # to exactly one output line, or '!' if resolution fails
            res = self.exec(f"""
                set -eu
                for hostname in {shlex.join(hostname for _, hostname in nodes_to_resolve)}; do
                    if entry=$(getent hosts "$hostname"); then
                        echo "$entry" | head -n 1
                    else
                        echo '!'
                    fi
                done
            """)
            if not res.ok:
                raise SlurmClientError(f"Failed to resolve IPs: {res}")
            host_lines = res.stdout.decode().strip().splitlines()
            if len(host_lines) != len(nodes_to_resolve):
                raise SlurmClientError(f"Failed to resolve IPs: unexpected output: {res}")
            for (node, hostname), host_line in zip(nodes_to_resolve, host_lines):
                if host_line.startswith("!"):
                    raise SlurmClientError(f"Failed to resolve hostname {hostname} to IP: {res}")
                ip = next(iter(host_line.split()), None)
                if ip is None:
                    raise SlurmClientError(f"Failed to resolve hostname {hostname} to IP: {res}")
                nodes.append(ResolvedNode(**dataclasses.asdict(node), hostname=hostname, ip=ip))

        nodes.sort(key=lambda n: n.name)
        return nodes

    def cancel_job(self, job_id: str) -> None:
        res = self.exec(f"scancel {job_id}")
        if not res.ok:
            raise SlurmClientError(f"Failed to cancel job: {res}")

    def exec(self, script: str, *, timeout: Optional[float] = None) -> ExecResult:
        """
        Execute a shell script using the user's login shell.
        The client must be already connected.
        """
        if self._client is None:
            raise SlurmClientError("Not connected")
        # boundary is used to strip pam's and/or shell's MOTD (or any other messages)
        boundary = f"__dstack_boundary_{uuid.uuid4().hex}__"
        _script = f"echo {boundary}; echo {boundary} >&2\n{script}\n"
        try:
            exit_status, stdout, stderr = self._exec(_script, self._get_timeout(timeout))
        except (paramiko.SSHException, OSError) as e:
            raise SlurmClientError(f"Failed to exec {script!r}: {e}") from e
        stdout = _strip_login_output(stdout, boundary)
        stderr = _strip_login_output(stderr, boundary)
        return ExecResult(
            exit_status=exit_status,
            stdout=stdout,
            stderr=stderr,
        )

    def _exec(self, script: str, timeout: float) -> tuple[int, bytes, bytes]:
        assert self._client is not None
        transport = self._client.get_transport()
        assert transport is not None
        chan = transport.open_session(timeout=timeout)
        # We use Channel.invoke_shell() ("shell" request) instead of Channel.exec_command() ("exec"
        # request) to get a login shell as if the user is logged in interactively
        try:
            chan.settimeout(timeout)
            chan.invoke_shell()
            chan.sendall(script.encode())
            chan.shutdown_write()
            stdout = chan.makefile("r", -1).read()
            stderr = chan.makefile_stderr("r", -1).read()
            exit_status = chan.recv_exit_status()
        finally:
            chan.close()
        return exit_status, stdout, stderr

    def _get_timeout(self, timeout: Optional[float] = None) -> float:
        return timeout or self._timeout


def _strip_login_output(output: bytes, boundary: str) -> bytes:
    _, sep, rest = output.partition(boundary.encode() + b"\n")
    return rest if sep else output


# A key starts at line-start or after whitespace: letters/digits/underscores then '='
_SINFO_SHOW_KEY_REGEX = re.compile(r"(?:^|\s)(?P<key>[A-Za-z_]\w*)=")


def _parse_scontrol_show_line(line: str, *, normalize_key: bool = True) -> dict[str, str]:
    line = line.strip()
    result = {}
    matches = list(_SINFO_SHOW_KEY_REGEX.finditer(line))
    for next_index, match in enumerate(matches, 1):
        key = match.group("key")
        if normalize_key:
            key = key.lower()
        value_start = match.end()
        value_end = matches[next_index].start() if next_index < len(matches) else len(line)
        result[key] = line[value_start:value_end].strip()
    return result


def _build_node_from_dict(node_dict: dict[str, str]) -> Node:
    name = node_dict.get("nodename")
    if not name:
        raise ValueError("Missing node name")

    cpus_raw = node_dict.get("cpuefctv")
    if not cpus_raw:
        cpus_raw = node_dict.get("cputot")
        if not cpus_raw:
            raise ValueError("Failed to detect CPU count")
    try:
        cpus = int(cpus_raw)
    except ValueError as e:
        raise ValueError(f"Failed to parse CPU count: {e}") from e

    memory_raw = node_dict.get("realmemory")
    if not memory_raw:
        raise ValueError("Failed to detect memory")
    try:
        memory_mib = int(memory_raw)
    except ValueError as e:
        raise ValueError(f"Failed to parse memory: {e}") from e

    return Node(
        name=name,
        arch=node_dict.get("arch"),
        cpus=cpus,
        memory_mib=memory_mib,
        gres=_split_by_comma(node_dict.get("gres", "")),
        partitions=_split_by_comma(node_dict.get("partitions", "")),
    )


def _split_by_comma(value: str) -> list[str]:
    # NB: empty items are unconditionally removed: "foo , , bar,,," -> ["foo", "bar"]
    return [item for _item in value.split(",") if (item := _item.strip())]
