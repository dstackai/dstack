import io
import logging
import tarfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from uuid import uuid4

import pytest
import yaml

from dstack._internal.cli.models.presets import PulledPreset
from dstack._internal.cli.services.presets import registry as registry_module
from dstack._internal.cli.services.presets.registry import (
    parse_registry_ref,
    pull_preset_from_registry,
    push_preset_to_registry,
    resolve_registry_client,
)
from dstack._internal.cli.services.presets.store import PresetStore
from dstack._internal.core.errors import (
    CLIError,
    MethodNotAllowedError,
    ResourceNotExistsError,
    URLNotFoundError,
)
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.files import (
    FileArchive,
    FileArchiveMapping,
    FilePathMapping,
)
from dstack._internal.core.models.presets import (
    PortablePreset,
    PresetSpec,
)
from dstack._internal.server.schemas.presets import (
    GetPresetResponse,
    PushPresetRequest,
    PushPresetResponse,
)
from dstack._internal.utils.files import create_file_archive
from dstack.api.server._presets import PresetsAPIClient
from tests._internal.cli.common import get_preset

pytestmark = pytest.mark.windows


class FakeFilesAPIClient:
    def __init__(self):
        self.uploads: list[SimpleNamespace] = []

    def upload_archive(self, hash, fp):
        archive = FileArchive(id=uuid4(), hash=hash)
        self.uploads.append(SimpleNamespace(hash=hash, content=fp.read(), archive=archive))
        return archive


class FakePresetsAPIClient:
    def __init__(self, remote: Optional[GetPresetResponse] = None):
        self.remote = remote
        self.push_requests: list[SimpleNamespace] = []
        self.file_requests: list[SimpleNamespace] = []
        # Blobs streamed by `get_files`, keyed by the archive mapping path.
        self.file_blobs: dict[str, bytes] = {}
        self.files = FakeFilesAPIClient()
        self.error: Optional[Exception] = None

    def push(self, project_name, name, spec):
        self._raise_if_failing()
        self.push_requests.append(SimpleNamespace(project_name=project_name, name=name, spec=spec))
        return _registry_preset_info(name=name)

    def get(self, project_name, name_or_id):
        self._raise_if_failing()
        assert self.remote is not None
        # The real client parses a fresh response object per request, so a caller
        # that re-roots the returned document cannot leak into the next pull.
        return self.remote.model_copy(deep=True)

    def get_files(self, project_name, name_or_id):
        self._raise_if_failing()
        self.file_requests.append(
            SimpleNamespace(project_name=project_name, name_or_id=name_or_id)
        )
        assert self.remote is not None
        # The server streams the archives the stored spec lists, not every blob
        # it happens to hold.
        return iter(
            (mapping.path, self.file_blobs[mapping.path])
            for mapping in self.remote.spec.file_archives
        )

    def _raise_if_failing(self):
        if self.error is not None:
            raise self.error


class FakeProjectsAPIClient:
    def __init__(self):
        self.error: Optional[Exception] = None

    def get(self, project_name):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(name=project_name)


def _registry_preset_info(*, name: Optional[str] = "qwen38") -> PushPresetResponse:
    return PushPresetResponse(
        id=uuid4(),
        name=name,
        project_name="main",
        base="Qwen/Qwen3.5-27B",
        repo="community/Qwen3.5-27B-GPTQ-Int4",
        created_at=datetime(2026, 8, 20, 12, 0),
        pushed_by="alice",
    )


def _portable_preset() -> PortablePreset:
    verified = get_preset()
    return PortablePreset(
        **{field: getattr(verified, field) for field in PortablePreset.model_fields}
    ).model_copy(deep=True)


def _registry_preset(
    *,
    name: Optional[str] = "qwen38",
    file_archives: Optional[list[FileArchiveMapping]] = None,
    file_mappings: Optional[list[FilePathMapping]] = None,
) -> GetPresetResponse:
    document = _portable_preset()
    if file_mappings is not None:
        document.service.files = file_mappings
    info = _registry_preset_info(name=name)
    return GetPresetResponse(
        **info.model_dump(),
        spec=PresetSpec(preset=document, file_archives=file_archives or []),
    )


def _file_archive_blob(tmp_path: Path, arcname: str, content: str) -> bytes:
    """A real archive, as `create_file_archive` produces on push: members rooted
    at the archived path's basename."""
    source_dir = tmp_path / "blob-sources" / uuid4().hex
    source_dir.mkdir(parents=True)
    source = source_dir / arcname
    source.write_text(content, encoding="utf-8")
    buffer = io.BytesIO()
    create_file_archive(source, buffer)
    return buffer.getvalue()


def _hostile_archive_blob(*members: tarfile.TarInfo) -> bytes:
    """A hand-built archive, as a malicious pusher can store one: the registry
    keeps archives as opaque blobs, so their members are untrusted."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for member in members:
            if member.isfile():
                archive.addfile(member, io.BytesIO(b"pwned"))
            else:
                archive.addfile(member)
    return buffer.getvalue()


def _file_member(name: str) -> tarfile.TarInfo:
    member = tarfile.TarInfo(name)
    member.type = tarfile.REGTYPE
    member.size = len(b"pwned")
    return member


def _symlink_member(name: str, linkname: str) -> tarfile.TarInfo:
    member = tarfile.TarInfo(name)
    member.type = tarfile.SYMTYPE
    member.linkname = linkname
    return member


def _archive_member_texts(blob: bytes) -> dict[str, str]:
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        return {
            member.name: archive.extractfile(member).read().decode("utf-8")
            for member in archive.getmembers()
            if member.isfile()
        }


@pytest.fixture
def stub_client(monkeypatch: pytest.MonkeyPatch):
    fake = FakePresetsAPIClient()
    fake.projects = FakeProjectsAPIClient()
    client = SimpleNamespace(
        presets=fake,
        files=fake.files,
        projects=fake.projects,
        base_url="http://test-server",
    )
    monkeypatch.setattr(registry_module, "resolve_registry_client", lambda project: client)
    return fake


class TestParseRegistryRef:
    def test_splits_on_the_first_slash(self):
        assert parse_registry_ref("main/qwen") == ("main", "qwen")
        assert parse_registry_ref("main/a/b") == ("main", "a/b")

    @pytest.mark.parametrize("ref", ["main", "main/", "/qwen", "/"])
    def test_rejects_incomplete_refs(self, ref):
        with pytest.raises(CLIError, match="Invalid registry reference"):
            parse_registry_ref(ref)


class TestResolveRegistryClient:
    def _configure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, projects: list[dict]):
        dstack_dir = tmp_path / ".dstack"
        dstack_dir.mkdir(parents=True, exist_ok=True)
        (dstack_dir / "config.yml").write_text(yaml.safe_dump({"projects": projects}))
        monkeypatch.setattr(
            "dstack._internal.core.services.configs.get_dstack_dir", lambda: dstack_dir
        )

    def test_uses_the_matching_config_entry(self, tmp_path, monkeypatch):
        self._configure(
            tmp_path,
            monkeypatch,
            [{"name": "main", "url": "http://my-server", "token": "t1", "default": True}],
        )

        client = resolve_registry_client("main")

        assert client.base_url == "http://my-server"
        assert client.token == "t1"

    def test_falls_back_to_sky_with_a_sky_entry_token(self, tmp_path, monkeypatch):
        self._configure(
            tmp_path,
            monkeypatch,
            [
                {"name": "local", "url": "http://localhost:3000", "token": "t1"},
                {"name": "mine", "url": "https://sky.dstack.ai", "token": "sky-token"},
            ],
        )

        client = resolve_registry_client("someone-elses-project")

        assert client.base_url == "https://sky.dstack.ai"
        assert client.token == "sky-token"

    def test_no_sky_fallback_env_disables_the_fallback(self, tmp_path, monkeypatch):
        self._configure(
            tmp_path,
            monkeypatch,
            [{"name": "mine", "url": "https://sky.dstack.ai", "token": "sky-token"}],
        )
        monkeypatch.setenv("DSTACK_NO_SKY_FALLBACK", "1")

        with pytest.raises(CLIError, match="dstack project add"):
            resolve_registry_client("someone-elses-project")

    def test_errors_without_any_usable_entry(self, tmp_path, monkeypatch):
        self._configure(
            tmp_path,
            monkeypatch,
            [{"name": "local", "url": "http://localhost:3000", "token": "t1"}],
        )

        with pytest.raises(CLIError, match="dstack project add"):
            resolve_registry_client("main")


class TestPresetsAPIClient:
    """The wire layer: what the client sends, and what it accepts back."""

    def _client(self, response) -> tuple[PresetsAPIClient, list[SimpleNamespace]]:
        calls: list[SimpleNamespace] = []

        def request(path, body=None, **kwargs):
            calls.append(SimpleNamespace(path=path, body=body, kwargs=kwargs))
            return response

        return PresetsAPIClient(request, logging.getLogger(__name__)), calls

    def test_push_sends_the_name_and_the_typed_spec(self):
        info = _registry_preset_info(name="qwen")
        client, calls = self._client(SimpleNamespace(json=lambda: info.model_dump(mode="json")))
        spec = PresetSpec(
            preset=_portable_preset(),
            file_archives=[FileArchiveMapping(id=uuid4(), path="/app/a.txt")],
        )

        pushed = client.push("main", name="qwen", spec=spec)

        (call,) = calls
        assert call.path == "/api/project/main/presets/push"
        sent = PushPresetRequest.model_validate_json(call.body)
        assert sent.name == "qwen"
        assert sent.spec == spec
        assert pushed.name == "qwen"
        assert pushed.repo == "community/Qwen3.5-27B-GPTQ-Int4"

    def test_get_returns_a_typed_spec_and_ignores_what_a_newer_server_adds(self):
        remote = _registry_preset()
        payload = remote.model_dump(mode="json")
        # A field only a newer server knows, at both levels of the response: an
        # older client must pull the preset unchanged rather than reject it.
        payload["a_newer_servers_field"] = "ignored"
        payload["spec"]["a_newer_servers_field"] = "ignored"
        payload["spec"]["preset"]["a_newer_servers_field"] = "ignored"
        client, _ = self._client(SimpleNamespace(json=lambda: payload))

        got = client.get("main", "qwen38")

        assert isinstance(got.spec, PresetSpec)
        assert got.spec.preset.repo == "community/Qwen3.5-27B-GPTQ-Int4"
        assert got.id == remote.id

    def test_get_files_reads_the_framed_stream(self):
        def frame(path: str, blob: bytes) -> bytes:
            return (
                len(path.encode()).to_bytes(4, "big")
                + path.encode()
                + len(blob).to_bytes(8, "big")
                + blob
            )

        stream = frame("patch/a.txt", b"tar-a") + frame("run.sh", b"tar-b")
        # Framed values are read across chunk boundaries, so a chunk size that
        # splits every frame is what proves the reader, not the framing.
        chunks = [stream[i : i + 3] for i in range(0, len(stream), 3)]
        client, calls = self._client(SimpleNamespace(iter_content=lambda chunk_size: iter(chunks)))

        got = list(client.get_files("main", "qwen38"))

        (call,) = calls
        assert call.path == "/api/project/main/presets/get_files"
        assert call.kwargs["stream"] is True
        assert got == [("patch/a.txt", b"tar-a"), ("run.sh", b"tar-b")]


class TestPushPresetToRegistry:
    def _save_preset_with_file(self, store: PresetStore) -> str:
        preset = get_preset()
        preset_dir = store.root / preset.id
        (preset_dir / "patch").mkdir(parents=True)
        (preset_dir / "patch" / "a.txt").write_text("hello", encoding="utf-8")
        preset.service.files = [
            FilePathMapping(local_path=str(preset_dir / "patch" / "a.txt"), path="/app/a.txt")
        ]
        store.save(preset)
        return preset.id

    def test_pushes_a_relativized_document_without_the_local_name(self, tmp_path, stub_client):
        store = PresetStore(tmp_path / "presets")
        preset_id = self._save_preset_with_file(store)

        push_preset_to_registry(store, preset_id, "main/qwen")

        (request,) = stub_client.push_requests
        assert request.project_name == "main"
        assert request.name == "qwen"
        # File contents travel as uploaded archives, referenced by id.
        (upload,) = stub_client.files.uploads
        assert request.spec.file_archives == [
            FileArchiveMapping(id=upload.archive.id, path="/app/a.txt")
        ]
        assert _archive_member_texts(upload.content) == {"a.txt": "hello"}
        document = request.spec.preset.model_dump(mode="json")
        # The pushed document is the bare artifact: no identity, no creation
        # context.
        assert "id" not in document
        assert "name" not in document
        assert "configuration" not in document
        assert "best_trial" not in document
        assert document["service"]["files"] == [
            {"local_path": "patch/a.txt", "path": "/app/a.txt"}
        ]

    def test_rejects_a_file_outside_the_preset_directory(self, tmp_path, stub_client):
        store = PresetStore(tmp_path / "presets")
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")
        preset = get_preset()
        preset.service.files = [FilePathMapping(local_path=str(outside), path="/app/a.txt")]
        store.save(preset)

        with pytest.raises(CLIError, match="outside the preset directory"):
            push_preset_to_registry(store, preset.id, "main/qwen")
        assert stub_client.push_requests == []
        assert stub_client.files.uploads == []

    def test_rejects_registry_auth_credentials_without_echoing_them(self, tmp_path, stub_client):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        preset.service.registry_auth = RegistryAuth(
            username="bot", password="canary-9f2kq-1234567890"
        )
        store.save(preset)

        with pytest.raises(CLIError, match="registry_auth") as excinfo:
            push_preset_to_registry(store, preset.id, "main/qwen")

        # The refusal must not become the leak it prevents.
        assert "canary-9f2kq-1234567890" not in str(excinfo.value)
        assert stub_client.push_requests == []
        assert stub_client.files.uploads == []

    @pytest.mark.parametrize("name", ["Qwen", "-qwen", "q wen", "q"])
    def test_rejects_an_invalid_registry_name(self, tmp_path, stub_client, name):
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)

        with pytest.raises(CLIError, match="Resource name"):
            push_preset_to_registry(store, preset.id, f"main/{name}")
        assert stub_client.push_requests == []

    def test_rejects_a_uuid_registry_name(self, tmp_path, stub_client):
        # A UUID name could later shadow another preset's id in ref resolution.
        store = PresetStore(tmp_path / "presets")
        preset = get_preset()
        store.save(preset)

        with pytest.raises(CLIError, match="must not be a UUID"):
            push_preset_to_registry(store, preset.id, "main/ab12cd34-ab12-4b12-8b12-ab12cd34ef56")
        assert stub_client.push_requests == []

    def test_rejects_a_missing_local_preset(self, tmp_path, stub_client):
        with pytest.raises(CLIError, match="'nope' does not exist"):
            push_preset_to_registry(PresetStore(tmp_path / "presets"), "nope", "main/qwen")

    @pytest.mark.parametrize(
        "error",
        [
            URLNotFoundError("Status code 404"),
            # A server whose routes match the path with another method.
            MethodNotAllowedError("Status code 405"),
        ],
        ids=["404", "405"],
    )
    def test_maps_a_missing_endpoint_to_a_registry_support_error(
        self, tmp_path, stub_client, error
    ):
        store = PresetStore(tmp_path / "presets")
        preset_id = self._save_preset_with_file(store)
        stub_client.error = error

        with pytest.raises(CLIError, match="does not support the preset registry"):
            push_preset_to_registry(store, preset_id, "main/qwen")


class TestPullPresetFromRegistry:
    def test_materializes_the_preset_under_its_qualified_name(self, tmp_path, stub_client):
        store = PresetStore(tmp_path / "presets")
        stub_client.remote = _registry_preset(
            file_archives=[FileArchiveMapping(id=uuid4(), path="/app/a.txt")],
            file_mappings=[FilePathMapping(local_path="patch/a.txt", path="/app/a.txt")],
        )
        stub_client.file_blobs["/app/a.txt"] = _file_archive_blob(tmp_path, "a.txt", "hello")
        preset_id = str(stub_client.remote.id)

        pull_preset_from_registry(store, "main/qwen38")

        pulled = store.get(preset_id)
        assert pulled is not None
        # A pulled copy is the bare artifact plus its local identity.
        assert isinstance(pulled, PulledPreset)
        # The local name is the qualified ref, so it can never collide with a
        # locally created preset.
        assert pulled.name == "main/qwen38"
        assert pulled.service.files[0].local_path == str(
            store.root / preset_id / "patch" / "a.txt"
        )
        assert (store.root / preset_id / "patch" / "a.txt").read_text() == "hello"
        # Files are downloaded by id, not by the pulled ref: a name may repoint
        # between requests. One request brings them all, however many there are.
        (file_request,) = stub_client.file_requests
        assert file_request.name_or_id == preset_id
        # The saved file keeps the path relative, like any locally created preset.
        saved = yaml.safe_load((store.root / preset_id / "preset.yml").read_text())
        assert saved["service"]["files"] == [{"local_path": "patch/a.txt", "path": "/app/a.txt"}]

    def test_does_not_touch_a_local_preset_with_the_unqualified_name(self, tmp_path, stub_client):
        store = PresetStore(tmp_path / "presets")
        local = get_preset().model_copy(update={"name": "qwen38"})
        store.save(local)
        stub_client.remote = _registry_preset()

        pull_preset_from_registry(store, "main/qwen38")

        assert store.get(local.id).name == "qwen38"
        assert store.get(str(stub_client.remote.id)).name == "main/qwen38"

    def test_repointing_a_name_releases_it_from_the_earlier_pull(self, tmp_path, stub_client):
        store = PresetStore(tmp_path / "presets")
        stub_client.remote = _registry_preset()
        first_id = str(stub_client.remote.id)
        pull_preset_from_registry(store, "main/qwen38")

        # The registry name now points at a newer version; re-pulling moves the
        # qualified name to the fresh copy silently, Docker-style.
        stub_client.remote = _registry_preset()
        second_id = str(stub_client.remote.id)
        pull_preset_from_registry(store, "main/qwen38")

        assert store.get(first_id).name is None
        assert store.get(second_id).name == "main/qwen38"
        assert store.find_by_name("main/qwen38").id == second_id

    def test_a_non_current_version_pulled_by_id_does_not_take_the_name(
        self, tmp_path, stub_client
    ):
        store = PresetStore(tmp_path / "presets")
        stub_client.remote = _registry_preset()
        current_id = str(stub_client.remote.id)
        pull_preset_from_registry(store, "main/qwen38")

        # An older version pulled by id lands untagged, like a Docker pull by
        # digest: the qualified name stays on the current version's copy.
        stub_client.remote = _registry_preset(name=None)
        old_id = str(stub_client.remote.id)
        pull_preset_from_registry(store, f"main/{old_id}")

        assert store.get(old_id).name is None
        assert store.get(current_id).name == "main/qwen38"
        assert store.find_by_name("main/qwen38").id == current_id

    def test_repulling_a_copy_by_id_keeps_the_name_it_already_holds(self, tmp_path, stub_client):
        # This copy took the qualified name when it was current. Re-pulling it by
        # id must not strip the name off the store, or local refs to it would
        # stop resolving.
        store = PresetStore(tmp_path / "presets")
        stub_client.remote = _registry_preset()
        preset_id = str(stub_client.remote.id)
        pull_preset_from_registry(store, "main/qwen38")

        stub_client.remote = _registry_preset(name=None).model_copy(
            update={"id": stub_client.remote.id}
        )
        pull_preset_from_registry(store, f"main/{preset_id}")

        assert store.get(preset_id).name == "main/qwen38"
        assert store.find_by_name("main/qwen38").id == preset_id

    def test_repulling_the_same_version_overwrites_in_place(self, tmp_path, stub_client):
        store = PresetStore(tmp_path / "presets")
        stub_client.remote = _registry_preset(
            file_archives=[FileArchiveMapping(id=uuid4(), path="/app/a.txt")],
            file_mappings=[FilePathMapping(local_path="patch/a.txt", path="/app/a.txt")],
        )
        stub_client.file_blobs["/app/a.txt"] = _file_archive_blob(tmp_path, "a.txt", "hello")
        preset_id = str(stub_client.remote.id)
        pull_preset_from_registry(store, "main/qwen38")

        stub_client.file_blobs["/app/a.txt"] = _file_archive_blob(tmp_path, "a.txt", "fresh")
        pull_preset_from_registry(store, "main/qwen38")

        assert store.get(preset_id).name == "main/qwen38"
        assert [path.parent.name for path in store.root.glob("*/preset.yml")] == [preset_id]
        assert (store.root / preset_id / "patch" / "a.txt").read_text() == "fresh"

    def test_repulling_a_shrunken_file_set_does_not_keep_the_stale_file(
        self, tmp_path, stub_client
    ):
        # The directory is replaced wholesale, so a file the preset no longer
        # carries must not survive into the next push.
        store = PresetStore(tmp_path / "presets")
        remote_id = uuid4()
        stub_client.remote = _registry_preset(
            file_archives=[
                FileArchiveMapping(id=uuid4(), path="/app/a.txt"),
                FileArchiveMapping(id=uuid4(), path="/app/b.txt"),
            ],
            file_mappings=[
                FilePathMapping(local_path="patch/a.txt", path="/app/a.txt"),
                FilePathMapping(local_path="patch/b.txt", path="/app/b.txt"),
            ],
        ).model_copy(update={"id": remote_id})
        stub_client.file_blobs["/app/a.txt"] = _file_archive_blob(tmp_path, "a.txt", "hello")
        stub_client.file_blobs["/app/b.txt"] = _file_archive_blob(tmp_path, "b.txt", "stale")
        pull_preset_from_registry(store, "main/qwen38")
        preset_id = str(remote_id)
        assert (store.root / preset_id / "patch" / "b.txt").exists()

        stub_client.remote = _registry_preset(
            file_archives=[FileArchiveMapping(id=uuid4(), path="/app/a.txt")],
            file_mappings=[FilePathMapping(local_path="patch/a.txt", path="/app/a.txt")],
        ).model_copy(update={"id": remote_id})
        pull_preset_from_registry(store, "main/qwen38")

        assert (store.root / preset_id / "patch" / "a.txt").read_text() == "hello"
        assert not (store.root / preset_id / "patch" / "b.txt").exists()
        saved = yaml.safe_load((store.root / preset_id / "preset.yml").read_text())
        assert saved["service"]["files"] == [{"local_path": "patch/a.txt", "path": "/app/a.txt"}]

    def test_rejects_a_traversing_file_path_before_writing(self, tmp_path, stub_client):
        store = PresetStore(tmp_path / "presets")
        stub_client.remote = _registry_preset(
            file_archives=[FileArchiveMapping(id=uuid4(), path="/app/a.txt")],
            file_mappings=[FilePathMapping(local_path="../evil.txt", path="/app/a.txt")],
        )

        with pytest.raises(CLIError, match="Invalid preset file path"):
            pull_preset_from_registry(store, "main/qwen38")
        assert not (store.root / str(stub_client.remote.id)).exists()
        assert not (tmp_path / "evil.txt").exists()
        assert stub_client.file_requests == []

    @pytest.mark.parametrize(
        ("paths", "error"),
        [
            # The store keeps the preset document at this path.
            (["preset.yml"], "reserved"),
            # `a` and `a/b` cannot both materialize on one filesystem.
            (["patch", "patch/a.txt"], "both a file and a directory"),
            # `:` covers Windows drive letters and is invalid on Windows targets.
            (["patch:a.txt"], "Invalid preset file path"),
            (["patch/../a.txt"], "Invalid preset file path"),
            (["/etc/a.txt"], "Invalid preset file path"),
        ],
    )
    def test_rejects_invalid_pulled_file_paths_before_writing(
        self, tmp_path, stub_client, paths, error
    ):
        store = PresetStore(tmp_path / "presets")
        stub_client.remote = _registry_preset(
            file_archives=[
                FileArchiveMapping(id=uuid4(), path=f"/app/{index}")
                for index, _ in enumerate(paths)
            ],
            file_mappings=[
                FilePathMapping(local_path=path, path=f"/app/{index}")
                for index, path in enumerate(paths)
            ],
        )

        with pytest.raises(CLIError, match=error):
            pull_preset_from_registry(store, "main/qwen38")
        assert not (store.root / str(stub_client.remote.id)).exists()
        assert stub_client.file_requests == []

    def test_rejects_a_mapping_not_included_in_the_pulled_files(self, tmp_path, stub_client):
        store = PresetStore(tmp_path / "presets")
        stub_client.remote = _registry_preset(
            file_mappings=[FilePathMapping(local_path="patch/a.txt", path="/app/a.txt")],
        )

        with pytest.raises(CLIError, match="missing from the push"):
            pull_preset_from_registry(store, "main/qwen38")

    def test_rejects_a_pulled_file_the_preset_does_not_reference(self, tmp_path, stub_client):
        store = PresetStore(tmp_path / "presets")
        stub_client.remote = _registry_preset(
            file_archives=[FileArchiveMapping(id=uuid4(), path="/app/orphan.txt")],
        )

        with pytest.raises(CLIError, match="not referenced"):
            pull_preset_from_registry(store, "main/qwen38")
        assert not (store.root / str(stub_client.remote.id)).exists()

    def test_maps_a_missing_preset_to_a_qualified_does_not_exist_error(
        self, tmp_path, stub_client
    ):
        # The server answers 400 + `resource_not_exists`, which the shared client
        # maps; the CLI names the qualified ref the user typed, not the bare one.
        stub_client.error = ResourceNotExistsError("Preset 'qwen38' does not exist")

        with pytest.raises(CLIError, match="'main/qwen38' does not exist"):
            pull_preset_from_registry(PresetStore(tmp_path / "presets"), "main/qwen38")

    def test_maps_a_missing_project_to_a_does_not_exist_error(self, tmp_path, stub_client):
        stub_client.error = URLNotFoundError("Status code 404")
        stub_client.projects.error = URLNotFoundError("Status code 404")

        with pytest.raises(CLIError, match="Project 'unknown-project' does not exist"):
            pull_preset_from_registry(PresetStore(tmp_path / "presets"), "unknown-project/qwen38")

    @pytest.mark.parametrize(
        "error",
        [
            URLNotFoundError("Status code 404"),
            # A server whose routes match the path with another method.
            MethodNotAllowedError("Status code 405"),
        ],
        ids=["404", "405"],
    )
    def test_maps_a_missing_endpoint_to_a_registry_support_error(
        self, tmp_path, stub_client, error
    ):
        stub_client.error = error

        with pytest.raises(CLIError, match="does not support the preset registry"):
            pull_preset_from_registry(PresetStore(tmp_path / "presets"), "main/qwen38")


class TestPulledArchiveMembers:
    """A registry archive is an opaque blob the pusher controls: extraction must
    never write outside the file it is materializing."""

    def _pull_hostile(self, tmp_path, stub_client, blob: bytes) -> PresetStore:
        store = PresetStore(tmp_path / "presets")
        stub_client.remote = _registry_preset(
            file_archives=[FileArchiveMapping(id=uuid4(), path="/app/a.txt")],
            file_mappings=[FilePathMapping(local_path="patch/a.txt", path="/app/a.txt")],
        )
        stub_client.file_blobs["/app/a.txt"] = blob
        return store

    def _assert_nothing_escaped(self, tmp_path, store: PresetStore, stub_client) -> None:
        # The failed pull leaves neither the escapee nor a half-materialized
        # directory without its preset document.
        assert not (store.root / str(stub_client.remote.id)).exists()
        assert not (tmp_path / "evil.txt").exists()
        assert not (tmp_path.parent / "evil.txt").exists()
        assert not (store.root / "evil.txt").exists()
        assert list(store.list()) == []

    def test_rejects_a_traversing_member_path(self, tmp_path, stub_client):
        store = self._pull_hostile(
            tmp_path, stub_client, _hostile_archive_blob(_file_member("a.txt/../../evil.txt"))
        )

        with pytest.raises(CLIError, match="unsafe member path"):
            pull_preset_from_registry(store, "main/qwen38")

        self._assert_nothing_escaped(tmp_path, store, stub_client)

    def test_rejects_a_symlink_member_escaping_the_directory(self, tmp_path, stub_client):
        store = self._pull_hostile(
            tmp_path,
            stub_client,
            _hostile_archive_blob(_symlink_member("a.txt", "../../../../evil.txt")),
        )

        with pytest.raises(CLIError, match="unsupported member type"):
            pull_preset_from_registry(store, "main/qwen38")

        self._assert_nothing_escaped(tmp_path, store, stub_client)

    def test_rejects_a_member_not_rooted_at_the_mapping_basename(self, tmp_path, stub_client):
        # Rooted inside the directory, but not at the file being materialized:
        # extracting it would write a file the preset does not declare.
        store = self._pull_hostile(
            tmp_path, stub_client, _hostile_archive_blob(_file_member("evil.txt"))
        )

        with pytest.raises(CLIError, match="unexpected member"):
            pull_preset_from_registry(store, "main/qwen38")

        self._assert_nothing_escaped(tmp_path, store, stub_client)

    def test_rejects_an_absolute_member_path(self, tmp_path, stub_client):
        store = self._pull_hostile(
            tmp_path, stub_client, _hostile_archive_blob(_file_member("/a.txt"))
        )

        with pytest.raises(CLIError, match="unsafe member path"):
            pull_preset_from_registry(store, "main/qwen38")

        self._assert_nothing_escaped(tmp_path, store, stub_client)

    def test_rejects_a_hostile_member_alongside_a_legitimate_one(self, tmp_path, stub_client):
        # Every member is checked before anything is extracted, so one bad member
        # rejects the whole archive rather than landing after the good ones.
        store = self._pull_hostile(
            tmp_path,
            stub_client,
            _hostile_archive_blob(_file_member("a.txt"), _file_member("a.txt/../../evil.txt")),
        )

        with pytest.raises(CLIError, match="unsafe member path"):
            pull_preset_from_registry(store, "main/qwen38")

        self._assert_nothing_escaped(tmp_path, store, stub_client)
