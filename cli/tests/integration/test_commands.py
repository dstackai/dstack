from pathlib import Path
from typing import List

from pytest import CaptureFixture

from dstack._internal.cli.config import CLIConfigManager
from tests.integration.common import hub_process, run_dstack_cli


class TestDstack:
    def test_prints_help_and_exists_with_0_exit_code(self, capsys: CaptureFixture):
        exit_code = run_dstack_cli([])
        assert exit_code == 0
        assert capsys.readouterr().out.startswith("Usage: dstack [-v] [-h] COMMAND ...")


class TestHub:
    def test_starts_and_configures_hub(self, dstack_dir):
        with hub_process(dstack_dir) as proc:
            assert "The server is available at" in proc.stdout.readline()
            default_project_config = CLIConfigManager(dstack_dir).get_default_project_config()
            assert default_project_config is not None


class TestConfig:
    def test_prints_error_if_hub_not_started(self, capsys: CaptureFixture):
        exit_code = run_dstack_cli(
            [
                "config",
                "--url",
                "http://127.0.0.1:31313",
                "--project",
                "project",
                "--token",
                "token",
            ]
        )
        assert exit_code == 1
        assert "Cannot connect to hub" in capsys.readouterr().out


class TestInit:
    def test_generates_default_ssh_key(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_local_repo: Path
    ):
        dstack_key_path = dstack_dir / "ssh" / "id_rsa"
        with hub_process(dstack_dir):
            assert not dstack_key_path.exists()
            exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_local_repo)
            assert exit_code == 0
            print(list(dstack_dir.iterdir()))
            assert dstack_key_path.exists()


class TestRun:
    def test_requires_config(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_local_repo: Path
    ):
        exit_code = run_dstack_cli(
            ["run", "bash", "-c", "echo hi"], dstack_dir=dstack_dir, repo_dir=tests_local_repo
        )
        assert exit_code == 1
        assert "No default project is configured" in capsys.readouterr().out

    def test_requires_init_for_remote_repo(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_public_repo: Path
    ):
        with hub_process(dstack_dir):
            exit_code = run_dstack_cli(
                ["run", "bash", "-c", "echo hi"], dstack_dir=dstack_dir, repo_dir=tests_public_repo
            )
            assert exit_code == 1
            assert "Call `dstack init` first" in capsys.readouterr().out

    def test_runs_workflow_from_bash_provider(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_local_repo: Path
    ):
        with hub_process(dstack_dir):
            exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_local_repo)
            assert exit_code == 0
            exit_code = run_dstack_cli(
                ["run", "bash", "-c", "echo 'Hello, world!'"],
                dstack_dir=dstack_dir,
                repo_dir=tests_local_repo,
            )
            assert exit_code == 0
            assert "Hello, world!" in capsys.readouterr().out

    def test_runs_workflow_from_yaml_file(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_public_repo: Path
    ):
        with hub_process(dstack_dir):
            exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_public_repo)
            assert exit_code == 0
            exit_code = run_dstack_cli(
                ["run", "hello"], dstack_dir=dstack_dir, repo_dir=tests_public_repo
            )
            assert exit_code == 0
            assert "Hello, world!" in capsys.readouterr().out


class TestArtifacts:
    def test_lists_artifacts(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_public_repo: Path
    ):
        with hub_process(dstack_dir):
            exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_public_repo)
            assert exit_code == 0
            capsys.readouterr()
            exit_code = run_dstack_cli(
                ["run", "artifacts-ls"], dstack_dir=dstack_dir, repo_dir=tests_public_repo
            )
            assert exit_code == 0
            run_name = _get_run_name_from_run_stdout(capsys.readouterr().out)
            exit_code = run_dstack_cli(
                ["ls", run_name], dstack_dir=dstack_dir, repo_dir=tests_public_repo
            )
            assert exit_code == 0
            expected_table = [
                ["ARTIFACT", "FILE", "SIZE"],
                ["dir1/", "dir12/"],
                ["dir2/dir22/", "2.txt", "2.0B"],
                ["22.txt", "2.0B"],
            ]
            _assert_table_output(capsys.readouterr().out, expected_table)
            exit_code = run_dstack_cli(
                ["ls", "-r", run_name], dstack_dir=dstack_dir, repo_dir=tests_public_repo
            )
            assert exit_code == 0
            expected_table = [
                ["ARTIFACT", "FILE", "SIZE"],
                ["dir1/", "dir12/1.txt", "2.0B"],
                ["dir12/11.txt", "2.0B"],
                ["dir2/dir22/", "2.txt", "2.0B"],
                ["22.txt", "2.0B"],
            ]
            _assert_table_output(capsys.readouterr().out, expected_table)


class TestDeps:
    def test_reads_artifacts_from_dep_workflow(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_public_repo: Path
    ):
        with hub_process(dstack_dir):
            exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_public_repo)
            assert exit_code == 0
            exit_code = run_dstack_cli(
                ["run", "hello-txt"], dstack_dir=dstack_dir, repo_dir=tests_public_repo
            )
            assert exit_code == 0
            exit_code = run_dstack_cli(
                ["run", "cat-txt-2"], dstack_dir=dstack_dir, repo_dir=tests_public_repo
            )
            assert exit_code == 0
            assert "Hello, world!" in capsys.readouterr().out


class TestSecrets:
    def test_adds_and_reads_secret(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_local_repo: Path
    ):
        with hub_process(dstack_dir):
            exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_local_repo)
            assert exit_code == 0
            exit_code = run_dstack_cli(
                ["secrets", "add", "MY_SECRET", "my_secret_value"],
                dstack_dir=dstack_dir,
                repo_dir=tests_local_repo,
            )
            assert exit_code == 0
            exit_code = run_dstack_cli(
                ["run", "bash", "-c", "echo $MY_SECRET"],
                dstack_dir=dstack_dir,
                repo_dir=tests_local_repo,
            )
            assert exit_code == 0
            assert "my_secret_value" in capsys.readouterr().out


def _get_run_name_from_run_stdout(run_stdout: str) -> str:
    run_line = run_stdout.splitlines()[1]
    return run_line.split()[0]


def _assert_table_output(output: str, expected_table: List[List[str]]):
    output_lines = output.splitlines()
    table = [l.split() for l in output_lines]
    assert table == expected_table
