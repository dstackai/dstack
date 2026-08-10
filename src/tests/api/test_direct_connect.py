from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from dstack._internal.core.errors import ClientError
from dstack._internal.core.models.runs import JobConnectionInfo, JobStatus, RunStatus
from dstack._internal.core.services.ssh.key_manager import UserSSHKey
from dstack._internal.utils.path import FilePath
from dstack._internal.utils.ssh import build_ssh_command, build_ssh_url_authority
from dstack.api._public import runs as public_runs
from dstack.api._public.runs import Run

_IDE_NAMES = {
    "vscode": "VS Code",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "zed": "Zed",
}


def _run_model(
    *,
    job_id: UUID,
    run_name: str = "dev-run",
    upstream_id: str | None = None,
    owner: str = "owner",
    status: RunStatus = RunStatus.RUNNING,
    job_status: JobStatus = JobStatus.RUNNING,
    configuration_type: str = "dev-environment",
    ide: str | None = "zed",
    hostname: str = "sshproxy.example.com",
    port: int | None = 2222,
    proxied_ssh_command: list[str] | None = None,
    proxied_ide_url: str | None = None,
    working_dir: str = "/workspace/project",
):
    if upstream_id is None:
        upstream_id = job_id.hex
    if proxied_ssh_command is None:
        proxied_ssh_command = build_ssh_command(
            username=upstream_id,
            hostname=hostname,
            port=port,
        )
    ide_name = _IDE_NAMES.get(ide) if ide is not None else None
    if proxied_ide_url is None and ide is not None:
        authority = build_ssh_url_authority(
            username=upstream_id,
            hostname=hostname,
            port=port,
        )
        if ide == "zed":
            proxied_ide_url = f"zed://ssh/{authority}{working_dir}"
        else:
            proxied_ide_url = f"{ide}://vscode-remote/ssh-remote+{authority}{working_dir}"
    connection_info = JobConnectionInfo(
        ide_name=ide_name,
        attached_ide_url=None,
        proxied_ide_url=proxied_ide_url,
        attached_ssh_command=["ssh", "ignored"],
        proxied_ssh_command=proxied_ssh_command,
        sshproxy_hostname=hostname,
        sshproxy_port=port,
        sshproxy_upstream_id=upstream_id,
    )
    job = SimpleNamespace(
        job_spec=SimpleNamespace(replica_num=0, job_num=0),
        job_submissions=[
            SimpleNamespace(
                status=job_status,
                job_runtime_data=SimpleNamespace(working_dir=working_dir),
            )
        ],
        job_connection_info=connection_info,
    )
    return SimpleNamespace(
        run_spec=SimpleNamespace(
            run_name=run_name,
            configuration=SimpleNamespace(type=configuration_type, ide=ide),
        ),
        jobs=[job],
        status=status,
        user=owner,
    )


def _api_client(run_model, *, username: str = "owner"):
    return SimpleNamespace(
        base_url="https://dstack.example.com",
        get_token_hash=lambda: "token-hash",
        runs=SimpleNamespace(get=Mock(return_value=run_model)),
        users=SimpleNamespace(get_my_user=Mock(return_value=SimpleNamespace(username=username))),
    )


@pytest.fixture
def local_connection_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config_manager = SimpleNamespace(
        dstack_ssh_dir=tmp_path,
        dstack_ssh_config_path=tmp_path / "config",
    )
    config_manager_factory = Mock(return_value=config_manager)
    key_manager = Mock()
    key_manager.return_value.get_user_key.return_value = UserSSHKey(
        public_key="ssh-ed25519 public",
        private_key_path=tmp_path / "private-key",
    )
    include = Mock()
    update = Mock()
    monkeypatch.setattr(public_runs, "ConfigManager", config_manager_factory)
    monkeypatch.setattr(public_runs, "UserSSHKeyManager", key_manager)
    monkeypatch.setattr(public_runs, "include_ssh_config", include)
    monkeypatch.setattr(public_runs, "update_ssh_config", update)
    return SimpleNamespace(
        config_manager_factory=config_manager_factory,
        key_manager=key_manager,
        include=include,
        update=update,
    )


def _assert_no_local_connection_state(state: SimpleNamespace) -> None:
    state.config_manager_factory.assert_not_called()
    state.key_manager.assert_not_called()
    state.include.assert_not_called()
    state.update.assert_not_called()


class TestRunGetDirectConnection:
    def test_returns_validated_argv_and_configures_current_job_alias(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        job_id = uuid4()
        run_model = _run_model(job_id=job_id)
        api_client = _api_client(run_model)
        run = Run(api_client=api_client, project="main", run=run_model)

        connection = run.get_direct_connection()

        assert connection.upstream_id == job_id.hex
        assert connection.ssh_command == ("ssh", f"{job_id.hex}@{connection.ssh_alias}")
        assert connection.ide == "zed"
        assert connection.ide_name == "Zed"
        assert connection.ide_command == (
            "zed",
            f"ssh://{job_id.hex}@{connection.ssh_alias}/workspace/project",
        )
        _, alias, raw_options = local_connection_config.update.call_args.args
        assert alias == connection.ssh_alias
        options = dict(raw_options)
        identity_file = options.pop("IdentityFile")
        assert isinstance(identity_file, FilePath)
        assert identity_file.path == (
            local_connection_config.config_manager_factory.return_value.dstack_ssh_dir
            / "private-key"
        )
        assert options == {
            "HostName": "sshproxy.example.com",
            "Port": 2222,
            "IdentitiesOnly": "yes",
        }
        local_connection_config.include.assert_called_once()
        api_client.runs.get.assert_called_once_with("main", "dev-run")

    def test_refreshes_job_id_on_every_resolution(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        stale_model = _run_model(job_id=uuid4())
        current_job_id = uuid4()
        current_model = _run_model(job_id=current_job_id)
        api_client = _api_client(current_model)
        run = Run(api_client=api_client, project="main", run=stale_model)

        connection = run.get_direct_connection()

        assert connection.upstream_id == current_job_id.hex
        assert connection.ssh_command == (
            "ssh",
            f"{current_job_id.hex}@{connection.ssh_alias}",
        )

    def test_defaults_a_missing_proxy_port_to_22(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        job_id = uuid4()
        run_model = _run_model(job_id=job_id, port=None)
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        connection = run.get_direct_connection()

        assert connection.sshproxy_port == 22
        assert connection.ssh_command == ("ssh", f"{job_id.hex}@{connection.ssh_alias}")
        assert local_connection_config.update.call_args.args[2]["Port"] == 22

    def test_expected_sshproxy_is_checked_before_local_state_changes(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        run_model = _run_model(job_id=uuid4())
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        with pytest.raises(ClientError, match="expected endpoint"):
            run.get_direct_connection(
                expected_sshproxy_hostname="other.example.com",
                expected_sshproxy_port=2222,
            )

        _assert_no_local_connection_state(local_connection_config)

    def test_rejects_non_owner_before_local_state_changes(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        run_model = _run_model(job_id=uuid4(), owner="another-user")
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        with pytest.raises(ClientError, match="run owner"):
            run.get_direct_connection()

        _assert_no_local_connection_state(local_connection_config)

    @pytest.mark.parametrize(
        ("status", "configuration_type", "message"),
        [
            (RunStatus.PENDING, "dev-environment", "requires a running run"),
            (RunStatus.RUNNING, "task", "only supported for dev environments"),
        ],
    )
    def test_requires_running_dev_environment(
        self,
        status: RunStatus,
        configuration_type: str,
        message: str,
        local_connection_config: SimpleNamespace,
    ) -> None:
        run_model = _run_model(
            job_id=uuid4(),
            status=status,
            configuration_type=configuration_type,
        )
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        with pytest.raises(ClientError, match=message):
            run.get_direct_connection()

        _assert_no_local_connection_state(local_connection_config)

    def test_rejects_explicit_replica_without_a_running_job(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        run_model = _run_model(job_id=uuid4(), job_status=JobStatus.TERMINATED)
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        with pytest.raises(ClientError, match="Failed to find running replica"):
            run.get_direct_connection(replica_num=0)

        _assert_no_local_connection_state(local_connection_config)

    def test_requires_server_proxy_connection_info(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        run_model = _run_model(job_id=uuid4())
        run_model.jobs[0].job_connection_info = None
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        with pytest.raises(ClientError, match="did not provide SSH proxy"):
            run.get_direct_connection()

        _assert_no_local_connection_state(local_connection_config)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda jci: setattr(jci, "sshproxy_hostname", "-oProxyCommand=bad"),
            lambda jci: setattr(jci, "sshproxy_hostname", "fe80::1%h"),
            lambda jci: setattr(jci, "sshproxy_port", True),
            lambda jci: setattr(jci, "sshproxy_port", 70000),
            lambda jci: setattr(jci, "sshproxy_upstream_id", "bad@upstream"),
            lambda jci: setattr(jci, "proxied_ssh_command", ["ssh", "other.example.com"]),
            lambda jci: setattr(jci, "ide_name", "Other IDE"),
            lambda jci: setattr(jci, "proxied_ide_url", "zed://ssh/untrusted/workspace"),
        ],
    )
    def test_rejects_inconsistent_or_unsafe_proxy_target(
        self,
        mutate,
        local_connection_config: SimpleNamespace,
    ) -> None:
        run_model = _run_model(job_id=uuid4())
        mutate(run_model.jobs[0].job_connection_info)
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        with pytest.raises(ClientError):
            run.get_direct_connection()

        _assert_no_local_connection_state(local_connection_config)

    @pytest.mark.parametrize(
        "working_dir",
        ["workspace/project", "/workspace/project\n-oProxyCommand=bad"],
    )
    def test_rejects_an_unsafe_working_directory(
        self,
        working_dir: str,
        local_connection_config: SimpleNamespace,
    ) -> None:
        run_model = _run_model(job_id=uuid4(), working_dir=working_dir)
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        with pytest.raises(ClientError, match="invalid dev environment working directory"):
            run.get_direct_connection()

        _assert_no_local_connection_state(local_connection_config)

    @pytest.mark.parametrize(
        ("ide", "ide_name", "executable"),
        [
            ("vscode", "VS Code", "code"),
            ("cursor", "Cursor", "cursor"),
            ("windsurf", "Windsurf", "windsurf"),
        ],
    )
    def test_returns_validated_vscode_family_command(
        self,
        ide: str,
        ide_name: str,
        executable: str,
        local_connection_config: SimpleNamespace,
    ) -> None:
        job_id = uuid4()
        run_model = _run_model(job_id=job_id, ide=ide)
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        connection = run.get_direct_connection()

        assert connection.ide == ide
        assert connection.ide_name == ide_name
        assert connection.ide_command == (
            executable,
            "--folder-uri",
            f"vscode-remote://ssh-remote+{job_id.hex}@{connection.ssh_alias}/workspace/project",
        )

    def test_does_not_offer_an_ide_for_an_ssh_only_configuration(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        run_model = _run_model(job_id=uuid4(), ide=None)
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        connection = run.get_direct_connection()

        assert connection.ide is None
        assert connection.ide_name is None
        assert connection.ide_command is None

    def test_rejects_unexpected_ide_info_for_an_ssh_only_configuration(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        run_model = _run_model(job_id=uuid4(), ide=None)
        run_model.jobs[0].job_connection_info.ide_name = "Zed"
        run_model.jobs[0].job_connection_info.proxied_ide_url = "zed://ssh/unexpected/workspace"
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        with pytest.raises(ClientError, match="unexpected IDE connection information"):
            run.get_direct_connection()

        _assert_no_local_connection_state(local_connection_config)

    def test_uses_distinct_aliases_for_concurrent_runs_in_one_project(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        first_model = _run_model(job_id=uuid4(), run_name="first-run")
        second_model = _run_model(job_id=uuid4(), run_name="second-run")
        first = Run(api_client=_api_client(first_model), project="main", run=first_model)
        second = Run(api_client=_api_client(second_model), project="main", run=second_model)

        first_connection = first.get_direct_connection()
        second_connection = second.get_direct_connection()

        assert first_connection.ssh_alias != second_connection.ssh_alias

    def test_accepts_an_extensible_safe_upstream_id(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        upstream_id = "runner.v2_job-01"
        run_model = _run_model(job_id=uuid4(), upstream_id=upstream_id)
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        connection = run.get_direct_connection()

        assert connection.upstream_id == upstream_id
        assert connection.ssh_command == ("ssh", f"{upstream_id}@{connection.ssh_alias}")

    @pytest.mark.parametrize("upstream_id", ["-leading-dash", "bad@id", "a" * 129])
    def test_rejects_an_unsafe_upstream_id(
        self,
        upstream_id: str,
        local_connection_config: SimpleNamespace,
    ) -> None:
        run_model = _run_model(job_id=uuid4(), upstream_id=upstream_id)
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        with pytest.raises(ClientError, match="invalid SSH proxy upstream ID"):
            run.get_direct_connection()

        _assert_no_local_connection_state(local_connection_config)

    def test_percent_encodes_the_zed_remote_path(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        job_id = uuid4()
        run_model = _run_model(
            job_id=job_id,
            working_dir="/workspace/a project/#literal%value",
        )
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        connection = run.get_direct_connection()

        assert connection.ide_command == (
            "zed",
            f"ssh://{job_id.hex}@{connection.ssh_alias}/workspace/a%20project/%23literal%25value",
        )

    def test_percent_encodes_a_vscode_family_remote_path(
        self,
        local_connection_config: SimpleNamespace,
    ) -> None:
        job_id = uuid4()
        run_model = _run_model(
            job_id=job_id,
            ide="cursor",
            working_dir="/workspace/a project/#literal%value",
        )
        run = Run(api_client=_api_client(run_model), project="main", run=run_model)

        connection = run.get_direct_connection()

        assert connection.ide_command == (
            "cursor",
            "--folder-uri",
            f"vscode-remote://ssh-remote+{job_id.hex}@{connection.ssh_alias}"
            "/workspace/a%20project/%23literal%25value",
        )
