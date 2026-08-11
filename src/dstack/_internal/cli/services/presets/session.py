"""Preset creation sessions: on-disk state, ownership, and liveness."""

import json
import os
import secrets
import shutil
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Optional

import psutil
import yaml
from rich.text import Text

from dstack._internal.cli.models.configurations import PresetConfiguration
from dstack._internal.cli.models.preset_agent import ClaudeAgentInfo
from dstack._internal.cli.utils.common import console
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError
from dstack._internal.utils.common import get_dstack_dir

if TYPE_CHECKING:
    from dstack._internal.cli.services.presets.agent import ClaudeAuth


_PROGRESS_FILENAME = "progress.jsonl"
_RUNS_FILENAME = "runs.jsonl"
_TRIALS_DIRNAME = "trials"
_SERVICE_DIRNAME = "service"
_TRIAL_RESULT_FILENAME = "trial.json"
_VERIFICATION_RESULT_FILENAME = "verification.json"
_CONSTRAINTS_FILENAME = "constraints.json"
_FINAL_REPORT_FILENAME = "final_report.json"
_SESSION_FILENAME = "session.json"
_USER_PROMPT_FILENAME = "user_prompt.md"


class SessionBusyError(CLIError):
    """Raised when another live process owns the session; view-only callers can
    fall back to a read-only follow."""


@dataclass
class PresetAgentSession:
    path: Path
    debug: bool
    preset_id: str = ""
    # Background reconcile sets this False so finalizing a detached session stays
    # silent on the read command; agent.log is written regardless.
    echo: bool = field(default=True, repr=False)
    _log_enabled: bool = field(default=True, init=False, repr=False)

    @property
    def log_path(self) -> Path:
        return self.path / "agent.log"

    @property
    def trace_path(self) -> Path:
        return self.path / "trace.jsonl"

    @property
    def runs_path(self) -> Path:
        return self.path / _RUNS_FILENAME

    @property
    def trials_dir(self) -> Path:
        return self.path / _TRIALS_DIRNAME

    @property
    def service_dir(self) -> Path:
        return self.path / _SERVICE_DIRNAME

    def write_prompt(self, prompt: str) -> None:
        _write_private_text(self.path / "prompt.md", prompt + "\n")

    def write_user_prompt(self, user_prompt: str) -> None:
        _write_private_text(self.path / _USER_PROMPT_FILENAME, user_prompt + "\n")

    def read_user_prompt(self) -> Optional[str]:
        try:
            text = (self.path / _USER_PROMPT_FILENAME).read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return text or None

    def write_constraints(self, constraints_text: str) -> None:
        _write_private_text(self.path / _CONSTRAINTS_FILENAME, constraints_text)

    def write_final_report(self, report_text: str) -> None:
        _write_private_text(self.path / _FINAL_REPORT_FILENAME, report_text)

    def write_agent_info(self, auth: "ClaudeAuth") -> None:
        from dstack._internal.cli.services.presets.agent import (
            _get_claude_auth_status,
            _get_claude_version,
        )

        info = ClaudeAgentInfo.model_validate(
            {
                "executable": auth.executable,
                "version": _get_claude_version(auth),
                "model": {
                    "name": auth.model,
                    "effort": auth.effort or "default",
                },
                "auth": _get_claude_auth_status(auth),
            }
        )
        _write_private_text(
            self.path / "agent.json",
            json.dumps(json.loads(info.model_dump_json()), indent=2) + "\n",
        )

    def append_log(self, line: str) -> None:
        if not self._log_enabled:
            return
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        except OSError as e:
            self._log_enabled = False
            if self.echo:
                console.print(f"[warning]Could not write agent log {self.log_path}: {e}[/]")

    def read_manifest(self) -> dict[str, Any]:
        try:
            manifest = json.loads((self.path / _SESSION_FILENAME).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return manifest if isinstance(manifest, dict) else {}

    def update_manifest(self, **fields: Any) -> None:
        manifest = self.read_manifest()
        manifest.update(fields)
        _write_private_text(self.path / _SESSION_FILENAME, json.dumps(manifest, indent=2) + "\n")

    def record_claude_session_id(self, session_id: str) -> None:
        self.update_manifest(claude_session_id=session_id)

    def finish(self, status: str) -> Path:
        self.update_manifest(status=status)
        return self.path


def get_presets_dir() -> Path:
    return get_dstack_dir() / "presets"


def create_preset_agent_session(
    configuration: PresetConfiguration,
    *,
    debug: bool = False,
) -> PresetAgentSession:
    if configuration.name is None:
        raise CLIError("The service name is required to save agent output")
    parent = get_presets_dir()
    path: Optional[Path] = None
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        while True:
            preset_id = secrets.token_hex(4)
            path = parent / preset_id
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                continue
            break
        _write_private_text(path / "agent.log", "")
        manifest = {
            "id": preset_id,
            "status": "running",
            "pid": os.getpid(),
            "pid_started_at": _process_started_at(os.getpid()),
            "name": configuration.name,
            "model": getattr(configuration.model, "base", None)
            or getattr(configuration.model, "repo", None),
            "trials_num": configuration.trials,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "debug": debug,
        }
        _write_private_text(path / _SESSION_FILENAME, json.dumps(manifest, indent=2) + "\n")
        data = json.loads(configuration.model_dump_json(exclude_none=True))
        if configuration.env:
            data["env"] = list(configuration.env)
        else:
            data.pop("env", None)
        _write_private_text(
            path / "preset.dstack.yml",
            yaml.safe_dump(data, sort_keys=False),
        )
        if debug:
            _write_private_text(path / "trace.jsonl", "")
    except OSError as e:
        if path is not None:
            shutil.rmtree(path, ignore_errors=True)
        raise CLIError(f"Could not create agent output under {parent}: {e}") from e
    assert path is not None
    return PresetAgentSession(path=path, debug=debug, preset_id=preset_id)


def load_resumable_agent_session(preset_id: str) -> PresetAgentSession:
    path = get_presets_dir() / preset_id
    session = PresetAgentSession(path=path, debug=False, preset_id=preset_id)
    manifest = session.read_manifest()
    if not path.is_dir() or not manifest:
        raise CLIError(f"Unknown preset: {preset_id}")
    status = manifest.get("status")
    if status == "success":
        raise CLIError(f"Preset {preset_id} is already created; nothing to resume")
    if status == "failed":
        raise CLIError(f"Preset {preset_id} creation failed and cannot be resumed")
    if status == "running" and session_process_alive(manifest):
        raise CLIError(
            f"Preset {preset_id} is still being created;"
            f" follow it with dstack preset logs -f {preset_id}"
        )
    if not manifest.get("claude_session_id"):
        raise CLIError(f"Preset {preset_id} creation stopped before it started; create a new one")
    session.debug = bool(manifest.get("debug"))
    return session


def _pid_alive(pid: Any, started_at: Any = None) -> bool:
    if not isinstance(pid, int) or pid <= 0 or not psutil.pid_exists(pid):
        return False
    if isinstance(started_at, (int, float)):
        create_time = _process_started_at(pid)
        # A recycled pid has a different start time.
        if create_time is not None and abs(create_time - started_at) > 1.0:
            return False
    return True


def session_process_alive(manifest: dict[str, Any]) -> bool:
    """True if either a live agent (possibly detached) or a live CLI (possibly
    between agent retries) still owns the session."""
    if _pid_alive(manifest.get("agent_pid"), manifest.get("agent_started_at")):
        return True
    pid = manifest.get("pid")
    if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
        return False
    # Guard the CLI pid with its start time: a recycled pid would otherwise read
    # a dead session as still owned, falsely blocking reconcile / follow.
    return _pid_alive(pid, manifest.get("pid_started_at"))


def load_attachable_agent_session(preset_id: str) -> PresetAgentSession:
    path = get_presets_dir() / preset_id
    session = PresetAgentSession(path=path, debug=False, preset_id=preset_id)
    manifest = session.read_manifest()
    if not path.is_dir() or not manifest:
        raise CLIError(f"Unknown preset: {preset_id}")
    status = manifest.get("status")
    if status == "success":
        raise CLIError(f"Preset {preset_id} is already created")
    if status == "failed":
        raise CLIError(f"Preset {preset_id} creation failed")
    if status == "interrupted":
        raise CLIError(
            f"Preset {preset_id} creation was interrupted; resume it with"
            f" dstack preset create -f <config> --resume {preset_id}"
        )
    pid = manifest.get("pid")
    if (
        isinstance(pid, int)
        and pid > 0
        and pid != os.getpid()
        and _pid_alive(pid, manifest.get("pid_started_at"))
    ):
        raise SessionBusyError(
            f"Preset {preset_id} is already being followed by another CLI (pid {pid});"
            f" stop or detach it there with Ctrl+C"
        )
    session.debug = bool(manifest.get("debug"))
    return session


def load_agent_session(preset_id: str) -> PresetAgentSession:
    path = get_presets_dir() / preset_id
    session = PresetAgentSession(path=path, debug=False, preset_id=preset_id)
    if not path.is_dir() or not session.read_manifest():
        raise CLIError(f"Unknown preset: {preset_id}")
    return session


def print_session_log(session: PresetAgentSession) -> None:
    try:
        content = session.log_path.read_text(encoding="utf-8")
    except OSError:
        content = ""
    if content.strip():
        console.print(Text(content.rstrip("\n")), soft_wrap=True)
    else:
        console.print(f"No log output yet for session [code]{session.preset_id}[/].")


def mark_session_owner(
    session: PresetAgentSession,
    *,
    project: Optional[str] = None,
    keep_service: Optional[bool] = None,
    claude_model: Optional[str] = None,
) -> None:
    """Beyond recording ownership, stores the finalize context a later detached
    reconcile needs; `None` fields are left untouched."""
    fields: dict[str, Any] = {
        "status": "running",
        "pid": os.getpid(),
        "pid_started_at": _process_started_at(os.getpid()),
    }
    if project is not None:
        fields["project"] = project
    if keep_service is not None:
        fields["keep_service"] = keep_service
    if claude_model is not None:
        fields["claude_model"] = claude_model
    session.update_manifest(**fields)


def session_report_exists(manifest: dict[str, Any]) -> bool:
    """True once the agent has written final_report.json, marking a detached
    session ready to finalize."""
    workspace = manifest.get("workspace")
    if not isinstance(workspace, str) or not workspace:
        return False
    return (Path(workspace) / "w" / _FINAL_REPORT_FILENAME).is_file()


def try_claim_session(session: PresetAgentSession) -> Optional[int]:
    """Takes an exclusive kernel lock so two readers can't both finalize the
    session; returns an fd to release via `release_session_claim`, or None if
    another process holds it. The kernel drops the lock if the holder dies, so
    there are no stale locks."""
    try:
        fd = os.open(session.path / ".reconcile.lock", os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return None
    if _try_lock_fd(fd):
        return fd
    with suppress(OSError):
        os.close(fd)
    return None


def release_session_claim(fd: Optional[int]) -> None:
    if fd is not None:
        # Closing the descriptor releases the kernel lock.
        with suppress(OSError):
            os.close(fd)


def _try_lock_fd(fd: int) -> bool:
    if IS_WINDOWS:
        import msvcrt

        try:
            # A 1-byte range lock at offset 0 (allowed past EOF on Windows).
            msvcrt.locking(  # pyright: ignore[reportAttributeAccessIssue]
                fd,
                msvcrt.LK_NBLCK,  # pyright: ignore[reportAttributeAccessIssue]
                1,
            )
            return True
        except OSError:
            return False
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def claimed_session_name(manifest: dict[str, Any]) -> Optional[str]:
    value = manifest.get("name")
    return value if isinstance(value, str) and value else None


def iter_agent_sessions() -> Iterator[PresetAgentSession]:
    """Skips dotfiles and `models--*` HuggingFace cache dirs that share the
    presets directory but aren't sessions."""
    root = get_presets_dir()
    if not root.is_dir():
        return
    for path in sorted(root.iterdir()):
        if path.is_dir() and not path.name.startswith((".", "models--")):
            yield PresetAgentSession(path=path, debug=False, preset_id=path.name)


def find_session_name_claims(name: str) -> list[PresetAgentSession]:
    """Sessions of any status holding `name`, including failed ones."""
    return [
        session
        for session in iter_agent_sessions()
        if claimed_session_name(session.read_manifest()) == name
    ]


def resolve_session_ref(ref: str) -> str:
    """A session reference may be a preset id or a claimed name."""
    if (get_presets_dir() / ref).is_dir():
        return ref
    claims = find_session_name_claims(ref)
    if len(claims) == 1:
        return claims[0].preset_id
    return ref


def list_agent_sessions() -> list[dict[str, Any]]:
    entries = []
    for session in iter_agent_sessions():
        path = session.path
        manifest = session.read_manifest()
        status = manifest.get("status")
        if status not in ("running", "interrupted", "success"):
            continue
        if status == "running" and not session_process_alive(manifest):
            status = "interrupted"
        entry = dict(manifest)
        entry["id"] = path.name
        entry["name"] = claimed_session_name(manifest)
        entry["status"] = status
        entry["trials"] = _summarize_session_trials(path / _TRIALS_DIRNAME)
        entry["verification"] = _read_last_session_verification(path / _SERVICE_DIRNAME)
        entry["constraints"] = _read_session_constraints(path)
        entries.append(entry)
    return entries


def _read_session_constraints(path: Path) -> dict[str, Any]:
    """Reads the session's own copy first: it outlives the agent workspace (removed
    once the session finishes). The workspace copy is a backward-compat fallback for
    sessions recorded before the session-level copy existed."""
    for candidate in (
        path / _CONSTRAINTS_FILENAME,
        path / "workspace" / "w" / _CONSTRAINTS_FILENAME,
    ):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def _numbered_subdirs(path: Path) -> list[Path]:
    try:
        entries = [entry for entry in path.iterdir() if entry.is_dir() and entry.name.isdigit()]
    except OSError:
        return []
    return sorted(entries, key=lambda entry: int(entry.name))


def _read_record(path: Path) -> Optional[dict[str, Any]]:
    """None if the record file is missing or caught half-written; the copy is
    retried, so treat None as transient, not final."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _read_last_session_verification(path: Path) -> Optional[dict[str, Any]]:
    """An attempt whose result file has not appeared yet is still in flight
    (reported as verifying)."""
    attempts = _numbered_subdirs(path)
    if not attempts:
        return None
    last = attempts[-1]
    record = _read_record(last / _VERIFICATION_RESULT_FILENAME)
    if record is not None and isinstance(record.get("status"), str):
        return record
    return {"status": "verifying"}


def _summarize_session_trials(path: Path) -> Optional[dict[str, Any]]:
    """A trial directory without `trial.json` is still in flight and is not
    counted."""
    records = []
    for trial_dir in _numbered_subdirs(path):
        record = _read_record(trial_dir / _TRIAL_RESULT_FILENAME)
        if record is not None:
            records.append(record)
    count = 0
    best: Optional[dict[str, Any]] = None
    # The fastest trial that broke a constraint, shown only when nothing passed.
    best_failed: Optional[dict[str, Any]] = None
    # One entry per trial in order, `None` for a trial that produced no benchmark.
    series: list[Optional[float]] = []
    # Parallel to `series`: True where the trial broke a constraint.
    failed: list[bool] = []
    # Kept outside `best` so a run where nothing passed still shows what it ran on.
    gpu: Optional[str] = None
    for record in records:
        count += 1
        benchmark = record.get("benchmark")
        failed.append(bool(record.get("failed")))
        record_gpu = _format_trial_gpu(record)
        if record_gpu:
            gpu = record_gpu
        if not isinstance(benchmark, dict):
            series.append(None)
            continue
        metrics = benchmark.get("metrics") or {}
        workload = benchmark.get("workload") or {}
        duration = metrics.get("duration_seconds")
        tokens = metrics.get("total_output_tokens")
        if not isinstance(duration, (int, float)) or duration <= 0:
            series.append(None)
            continue
        if not isinstance(tokens, (int, float)):
            series.append(None)
            continue
        tok_s = tokens / duration
        series.append(tok_s)
        # A failed trial keeps its benchmark — it is what the next trial learns
        # from — but it is not a candidate for best, and promoting one would put
        # a configuration that broke a constraint at the top of the listing.
        if record.get("failed"):
            if best_failed is None or tok_s > best_failed["tok_s"]:
                best_failed = _trial_entry(tok_s, record, metrics, workload, record_gpu)
            continue
        if best is None or tok_s > best["tok_s"]:
            best = _trial_entry(tok_s, record, metrics, workload, record_gpu)
    return {
        "count": count,
        "best": best,
        "best_failed": best_failed,
        "series": series,
        "failed": failed,
        "gpu": gpu,
    }


def _trial_entry(
    tok_s: float,
    record: dict[str, Any],
    metrics: dict[str, Any],
    workload: dict[str, Any],
    gpu: Optional[str],
) -> dict[str, Any]:
    ttft = (metrics.get("ttft_ms") or {}).get("p50")
    tpot = (metrics.get("tpot_ms") or {}).get("p50")
    context_length = record.get("context_length")
    return {
        "tok_s": tok_s,
        "tpot_ms": tpot if isinstance(tpot, (int, float)) and tpot > 0 else None,
        "ttft_ms": ttft if isinstance(ttft, (int, float)) else None,
        "context_length": context_length if isinstance(context_length, int) else None,
        "concurrency": workload.get("concurrency"),
        "gpu": gpu,
    }


def _format_trial_gpu(record: dict[str, Any]) -> Optional[str]:
    resources = record.get("resources")
    gpu = resources.get("gpu") if isinstance(resources, dict) else None
    if not isinstance(gpu, dict) or not gpu.get("name"):
        return None
    text = str(gpu["name"])
    if gpu.get("memory"):
        text += f":{gpu['memory']}"
    if gpu.get("count"):
        text += f":{gpu['count']}"
    return text


def print_preset_progress(message: str, *, agent_session: PresetAgentSession) -> None:
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    message = message.rstrip("\r\n")
    agent_session.append_log(f"[{timestamp}] {message}")
    if not agent_session.echo:
        return
    console.print(
        Text(f"[{timestamp}]", style="log.time"),
        Text(message, style="log.message"),
        soft_wrap=True,
    )


def _pid_running(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _process_started_at(pid: int) -> Optional[float]:
    try:
        return psutil.Process(pid).create_time()
    except psutil.Error:
        return None


def _write_private_bytes(path: Path, content: bytes) -> None:
    # Atomic tmp + fsync + replace (mkstemp already creates the file 0600), so
    # a crash mid-write cannot leave a truncated manifest or offsets file.
    # Binary mode: mirrored files are copies, and text mode rewrites newlines.
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(temporary, path)
        except PermissionError:
            if not IS_WINDOWS:
                raise
            # A concurrent reader (a viewer polling the manifest) can hold the
            # destination open without FILE_SHARE_DELETE; retry briefly, then
            # prefer an in-place write over crashing the owner.
            for _ in range(3):
                time.sleep(0.01)
                with suppress(PermissionError):
                    os.replace(temporary, path)
                    return
            path.write_bytes(content)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary)


def _write_private_text(path: Path, content: str) -> None:
    _write_private_bytes(path, content.encode("utf-8"))
