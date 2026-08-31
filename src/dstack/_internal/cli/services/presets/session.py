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
from typing import TYPE_CHECKING, Any, Iterator, Optional, Sequence

import psutil
import yaml
from pydantic import ValidationError
from rich.text import Text

from dstack._internal.cli.models.preset_agent import (
    PresetSessionFinalize,
    PresetSessionProcess,
    PresetSessionRun,
    PresetSessionState,
    PresetSessionStatus,
    PresetSessionWorkspace,
)
from dstack._internal.cli.utils.common import console
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.configurations import PresetConfiguration
from dstack._internal.utils.common import get_dstack_dir

if TYPE_CHECKING:
    from dstack._internal.cli.services.presets.agent import ClaudeAuth


_PROGRESS_FILENAME = "progress.jsonl"
_RUNS_FILENAME = "runs.jsonl"
TRIALS_DIRNAME = "trials"
SERVICE_DIRNAME = "service"
TRIAL_RESULT_FILENAME = "trial.json"
VERIFICATION_RESULT_FILENAME = "verification.json"
_CONSTRAINTS_FILENAME = "constraints.json"
_FINAL_REPORT_FILENAME = "final_report.json"
_SESSION_FILENAME = "session.json"
_USER_PROMPT_FILENAME = "user_prompt.md"


class SessionBusyError(CLIError):
    """Raised when another live process owns the session; view-only callers can
    fall back to a read-only follow."""


@dataclass
class PresetSession:
    path: Path
    preset_id: str
    # Background reconcile sets this False so finalizing a detached session stays
    # silent on the read command; agent.log is written regardless.
    echo: bool = field(default=True, repr=False)
    _log_enabled: bool = field(default=True, init=False, repr=False)

    @property
    def created_at(self) -> datetime:
        state = self.read_state()
        if state is None:
            raise CLIError(f"Unknown preset session {self.preset_id}")
        return state.created_at

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
        return self.path / TRIALS_DIRNAME

    @property
    def service_dir(self) -> Path:
        return self.path / SERVICE_DIRNAME

    def write_prompt(self, prompt: str) -> None:
        _write_private_text(self.path / "prompt.md", prompt + "\n")

    def read_prompt(self) -> Optional[str]:
        path = self.path / "prompt.md"
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8").strip() or None

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

        # `agent.json`: a debug document written once and read by nothing, so it
        # is a plain dump, not a model.
        info = {
            "executable": auth.executable,
            "version": _get_claude_version(auth),
            "model": {"name": auth.model, "effort": auth.effort or "default"},
            "auth_status": _get_claude_auth_status(auth),
        }
        _write_private_text(self.path / "agent.json", json.dumps(info, indent=2) + "\n")

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

    def read_state(self) -> Optional[PresetSessionState]:
        """None marks a session with no readable state: never created, or corrupt."""
        try:
            data = json.loads((self.path / _SESSION_FILENAME).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(data, dict) and "run" not in data and ("pid" in data or "workspace" in data):
            data = _upgrade_pre_0_21_2_state(data)
        try:
            return validate_extra_ignore(PresetSessionState, data)
        except ValidationError:
            return None

    def write_state(self, state: PresetSessionState) -> None:
        _write_private_text(
            self.path / _SESSION_FILENAME,
            state.model_dump_json(indent=2) + "\n",
        )

    def begin_run(
        self,
        *,
        workspace: PresetSessionWorkspace,
        finalize: PresetSessionFinalize,
        claude_model: Optional[str],
    ) -> None:
        """This CLI takes ownership and starts (or joins) the agent run. Everything
        an earlier run established survives: the claude session id and model pin so
        a resume finds them, and the agent process reference so following a live
        detached agent keeps it alive instead of reading it as dead."""
        state = self.read_state()
        if state is None:
            raise CLIError(f"Preset {self.preset_id} session state is unreadable")
        earlier = state.run
        state.status = "running"
        state.owner = _current_process()
        state.run = PresetSessionRun(
            workspace=workspace,
            finalize=finalize,
            claude_model=claude_model or (earlier.claude_model if earlier else None),
            agent=earlier.agent if earlier else None,
            claude_session_id=earlier.claude_session_id if earlier else None,
        )
        self.write_state(state)

    def record_agent(self, agent: PresetSessionProcess) -> None:
        state = self.read_state()
        if state is None or state.run is None:
            return
        state.run.agent = agent
        self.write_state(state)

    def record_claude_session_id(self, session_id: str) -> None:
        # An unreadable state stays as it is: rewriting it would fabricate a
        # session record out of one field.
        state = self.read_state()
        if state is None or state.run is None:
            return
        state.run.claude_session_id = session_id
        self.write_state(state)

    def detach(self) -> None:
        state = self.read_state()
        if state is None:
            return
        state.owner = None
        self.write_state(state)

    def release_name(self) -> None:
        state = self.read_state()
        if state is None:
            return
        state.name = None
        self.write_state(state)

    def finish(self, status: PresetSessionStatus) -> Path:
        state = self.read_state()
        if state is not None:
            state.status = status
            self.write_state(state)
        return self.path


# TODO: Remove in 0.22
def _upgrade_pre_0_21_2_state(data: dict[str, Any]) -> dict[str, Any]:
    """A session file from before 0.21.2 held every field flat; the same facts now
    live in `owner` and `run`. Pure regrouping for backward compatibility."""
    data = dict(data)
    pid = data.pop("pid", None)
    pid_started_at = data.pop("pid_started_at", None)
    data["owner"] = {"pid": pid, "started_at": pid_started_at} if pid is not None else None
    workspace = data.pop("workspace", None)
    alias = data.pop("alias", None)
    agent_pid = data.pop("agent_pid", None)
    agent_started_at = data.pop("agent_started_at", None)
    project = data.pop("project", None)
    keep_service = data.pop("keep_service", None)
    claude_model = data.pop("claude_model", None)
    claude_session_id = data.pop("claude_session_id", None)
    if workspace is None or project is None:
        # Without the finalize context there is no run to reconcile or resume.
        data["run"] = None
    else:
        data["run"] = {
            "workspace": {"path": workspace, "alias": alias or workspace},
            "finalize": {"project": project, "keep_service": bool(keep_service)},
            "claude_model": claude_model,
            "agent": (
                {"pid": agent_pid, "started_at": agent_started_at}
                if agent_pid is not None
                else None
            ),
            "claude_session_id": claude_session_id,
        }
    data.setdefault("previous", [])
    return data


def get_presets_dir() -> Path:
    return get_dstack_dir() / "presets"


def create_preset_session(
    configuration: PresetConfiguration,
    *,
    previous: Sequence[str],
) -> PresetSession:
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
        _write_private_text(path / "trace.jsonl", "")
        session = PresetSession(path=path, preset_id=preset_id)
        session.write_state(
            PresetSessionState(
                id=preset_id,
                name=configuration.name,
                model=configuration.model.exact_repo or configuration.model.api_model_name,
                trials_num=configuration.trials,
                previous=list(previous),
                created_at=datetime.now(timezone.utc),
                status="running",
                owner=_current_process(),
                run=None,
            )
        )
        record = configuration.model_dump(mode="json", exclude_none=True)
        # Env values may be secrets: the session records only the variable names,
        # which read back as passthrough references resolved from the environment.
        record["env"] = list(configuration.env)
        if not configuration.env:
            record.pop("env")
        _write_private_text(
            path / "preset.dstack.yml",
            yaml.safe_dump(record, sort_keys=False),
        )
    except OSError as e:
        if path is not None:
            shutil.rmtree(path, ignore_errors=True)
        raise CLIError(f"Could not create agent output under {parent}: {e}") from e
    return session


def load_resumable_session(preset_id: str) -> PresetSession:
    path = get_presets_dir() / preset_id
    session = PresetSession(path=path, preset_id=preset_id)
    state = session.read_state()
    if not path.is_dir() or state is None:
        raise CLIError(f"Unknown preset: {preset_id}")
    if state.status == "success":
        raise CLIError(f"Preset {preset_id} is already created; nothing to resume")
    if state.status == "failed":
        raise CLIError(f"Preset {preset_id} creation failed and cannot be resumed")
    if state.status == "running" and session_process_alive(state):
        raise CLIError(
            f"Preset {preset_id} is still being created;"
            f" follow it with dstack preset logs -f {preset_id}"
        )
    if state.run is None or state.run.claude_session_id is None:
        raise CLIError(f"Preset {preset_id} creation stopped before it started; create a new one")
    return session


def _current_process() -> PresetSessionProcess:
    return PresetSessionProcess(pid=os.getpid(), started_at=process_started_at(os.getpid()))


def process_alive(process: Optional[PresetSessionProcess]) -> bool:
    if process is None or process.pid <= 0 or not psutil.pid_exists(process.pid):
        return False
    if process.started_at is not None:
        create_time = process_started_at(process.pid)
        # A recycled pid has a different start time.
        if create_time is not None and abs(create_time - process.started_at) > 1.0:
            return False
    return True


def session_process_alive(state: PresetSessionState) -> bool:
    """True if either a live agent (possibly detached) or a live CLI (possibly
    between agent retries) still owns the session."""
    if state.run is not None and process_alive(state.run.agent):
        return True
    if state.owner is None or state.owner.pid == os.getpid():
        return False
    return process_alive(state.owner)


def load_attachable_session(preset_id: str) -> PresetSession:
    path = get_presets_dir() / preset_id
    session = PresetSession(path=path, preset_id=preset_id)
    state = session.read_state()
    if not path.is_dir() or state is None:
        raise CLIError(f"Unknown preset: {preset_id}")
    if state.status == "success":
        raise CLIError(f"Preset {preset_id} is already created")
    if state.status == "failed":
        raise CLIError(f"Preset {preset_id} creation failed")
    if state.status == "interrupted":
        raise CLIError(
            f"Preset {preset_id} creation was interrupted; resume it with"
            f" dstack preset create -f <config> --resume {preset_id}"
        )
    owner = state.owner
    if owner is not None and owner.pid != os.getpid() and process_alive(owner):
        raise SessionBusyError(
            f"Preset {preset_id} is already being followed by another CLI (pid {owner.pid});"
            f" stop or detach it there with Ctrl+C"
        )
    return session


def load_preset_session(preset_id: str) -> PresetSession:
    path = get_presets_dir() / preset_id
    session = PresetSession(path=path, preset_id=preset_id)
    if not path.is_dir() or session.read_state() is None:
        raise CLIError(f"Unknown preset: {preset_id}")
    return session


def print_session_log(session: PresetSession) -> None:
    try:
        content = session.log_path.read_text(encoding="utf-8")
    except OSError:
        content = ""
    if content.strip():
        console.print(Text(content.rstrip("\n")), soft_wrap=True)
    else:
        console.print(f"No log output yet for session [code]{session.preset_id}[/].")


def session_report_exists(state: PresetSessionState) -> bool:
    """True once the agent has written final_report.json, marking a detached
    session ready to finalize."""
    if state.run is None:
        return False
    return (Path(state.run.workspace.path) / "w" / _FINAL_REPORT_FILENAME).is_file()


def try_claim_session(session: PresetSession) -> Optional[int]:
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


def claimed_session_name(state: PresetSessionState) -> Optional[str]:
    return state.name or None


def iter_preset_sessions() -> Iterator[PresetSession]:
    """Skips dotfiles and `models--*` HuggingFace cache dirs that share the
    presets directory but aren't sessions."""
    root = get_presets_dir()
    if not root.is_dir():
        return
    for path in sorted(root.iterdir()):
        if path.is_dir() and not path.name.startswith((".", "models--")):
            yield PresetSession(path=path, preset_id=path.name)


def find_session_name_claims(name: str) -> list[PresetSession]:
    """Sessions of any status holding `name`, including failed ones."""
    return [
        session
        for session in iter_preset_sessions()
        if (state := session.read_state()) is not None and claimed_session_name(state) == name
    ]


def resolve_session_ref(ref: str) -> str:
    """A session reference may be a preset id or a claimed name."""
    if (get_presets_dir() / ref).is_dir():
        return ref
    claims = find_session_name_claims(ref)
    if len(claims) == 1:
        return claims[0].preset_id
    return ref


def list_preset_sessions() -> list[dict[str, Any]]:
    entries = []
    for session in iter_preset_sessions():
        path = session.path
        state = session.read_state()
        if state is None:
            continue
        status = state.status
        if status == "running" and not session_process_alive(state):
            status = "interrupted"
        entry = state.model_dump(mode="json")
        entry["id"] = path.name
        entry["name"] = claimed_session_name(state)
        entry["status"] = status
        entry["trials"] = _summarize_session_trials(path / TRIALS_DIRNAME)
        entry["verification"] = _read_last_session_verification(path / SERVICE_DIRNAME)
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
    record = _read_record(last / VERIFICATION_RESULT_FILENAME)
    if record is not None and isinstance(record.get("status"), str):
        return record
    return {"status": "verifying"}


def _summarize_session_trials(path: Path) -> Optional[dict[str, Any]]:
    # TODO: Refactor this crap - must be explicit what is this and where is it used; also dicts are prohibited in dstack repo
    """A trial directory without `trial.json` is still in flight and is not
    counted."""
    records = []
    for trial_dir in _numbered_subdirs(path):
        record = _read_record(trial_dir / TRIAL_RESULT_FILENAME)
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
    # Mean, not p50: MTP skews TPOT right, and mean is the delivered decode rate.
    tpot = (metrics.get("tpot_ms") or {}).get("mean")
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
    """A trial on one instance records a flat `resources` object; a trial that
    used node groups records `groups` instead."""
    counts: dict[str, int] = {}
    for node in _trial_nodes(record):
        spec = _format_gpu(node.get("gpu"))
        if spec:
            # Insertion order is group order, so the roles read in the order they ran.
            counts[spec] = counts.get(spec, 0) + 1
    if not counts:
        return None
    return " + ".join(spec if n == 1 else f"{spec} x{n}" for spec, n in counts.items())


def _trial_nodes(record: dict[str, Any]) -> list[dict[str, Any]]:
    groups = record.get("groups")
    if isinstance(groups, list):
        return [
            node
            for group in groups
            if isinstance(group, list)
            for node in group
            if isinstance(node, dict)
        ]
    resources = record.get("resources")
    return [resources] if isinstance(resources, dict) else []


def _format_gpu(gpu: Any) -> Optional[str]:
    if not isinstance(gpu, dict) or not gpu.get("name"):
        return None
    text = str(gpu["name"])
    if gpu.get("memory"):
        text += f":{gpu['memory']}"
    if gpu.get("count"):
        text += f":{gpu['count']}"
    return text


def print_preset_progress(message: str, *, session: PresetSession) -> None:
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    message = message.rstrip("\r\n")
    session.append_log(f"[{timestamp}] {message}")
    if not session.echo:
        return
    console.print(
        Text(f"[{timestamp}]", style="log.time"),
        Text(message, style="log.message"),
        soft_wrap=True,
    )


def pid_running(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def process_started_at(pid: int) -> Optional[float]:
    try:
        return psutil.Process(pid).create_time()
    except psutil.Error:
        return None


def _write_private_bytes(path: Path, content: bytes) -> None:
    # Atomic tmp + fsync + replace (mkstemp already creates the file 0600), so
    # a crash mid-write cannot leave a truncated state or offsets file.
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
            # A concurrent reader (a viewer polling the state) can hold the
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
