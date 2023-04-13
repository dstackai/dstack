from pathlib import Path
from typing import List

from pytest import CaptureFixture

from tests.integration.common import run_dstack_cli


class TestDstack:
    def test_prints_help_and_exists_with_0_exit_code(self, capsys: CaptureFixture):
        exit_code = run_dstack_cli([])
        assert exit_code == 0
        assert capsys.readouterr().out.startswith("Usage: dstack [-v] [-h] COMMAND ...")


class TestInit:
    def test_warns_if_no_ssh_key(
        self, capsys: CaptureFixture, tests_public_repo: Path, dstack_dir: Path
    ):
        exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_public_repo)
        assert exit_code == 0
        stdout = capsys.readouterr().out
        assert "WARNING" in stdout and "SSH is not enabled" in stdout

    def test_inits_local_backend(
        self, capsys: CaptureFixture, tests_public_repo: Path, dstack_dir: Path, ssh_key
    ):
        exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_public_repo)
        assert exit_code == 0
        assert "OK (backend: local)" in capsys.readouterr().out


class TestRun:
    def test_cannot_run_outside_of_git_repo(self, capsys: CaptureFixture):
        exit_code = run_dstack_cli(["run", "bash"])
        assert exit_code == 1
        assert "is not a Git repo" in capsys.readouterr().out

    def test_asks_for_init_to_run(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_public_repo: Path
    ):
        exit_code = run_dstack_cli(
            ["run", "bash"], dstack_dir=dstack_dir, repo_dir=tests_public_repo
        )
        assert exit_code == 1
        assert "Call `dstack init` first" in capsys.readouterr().out

    def test_runs_workflow_from_bash_provider(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_public_repo: Path, ssh_key
    ):
        exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_public_repo)
        assert exit_code == 0
        exit_code = run_dstack_cli(
            ["run", "bash", "-c", "echo Hello, world!"],
            dstack_dir=dstack_dir,
            repo_dir=tests_public_repo,
        )
        assert exit_code == 0
        assert "Hello, world!" in capsys.readouterr().out

    def test_runs_workflow_from_yaml_file(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_public_repo: Path, ssh_key
    ):
        exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_public_repo)
        assert exit_code == 0
        exit_code = run_dstack_cli(
            ["run", "hello"], dstack_dir=dstack_dir, repo_dir=tests_public_repo
        )
        assert exit_code == 0
        assert "Hello, world!" in capsys.readouterr().out


class TestArtifacts:
    def test_lists_artifacts(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_public_repo: Path, ssh_key
    ):
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
            ["ARTIFACT", "FILE", "SIZE", "BACKENDS"],
            ["dir1/", "dir12/", "local"],
            ["dir2/dir22/", "2.txt", "2.0B", "local"],
            ["22.txt", "2.0B", "local"],
        ]
        _assert_table_output(capsys.readouterr().out, expected_table)
        exit_code = run_dstack_cli(
            ["ls", "-r", run_name], dstack_dir=dstack_dir, repo_dir=tests_public_repo
        )
        assert exit_code == 0
        expected_table = [
            ["ARTIFACT", "FILE", "SIZE", "BACKENDS"],
            ["dir1/", "dir12/1.txt", "2.0B", "local"],
            ["dir12/11.txt", "2.0B", "local"],
            ["dir2/dir22/", "2.txt", "2.0B", "local"],
            ["22.txt", "2.0B", "local"],
        ]
        _assert_table_output(capsys.readouterr().out, expected_table)


class TestDeps:
    def test_reads_artifacts_from_dep_workflow(
        self, capsys: CaptureFixture, dstack_dir: Path, tests_public_repo: Path, ssh_key
    ):
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
        self, capsys: CaptureFixture, dstack_dir: Path, tests_public_repo: Path, ssh_key
    ):
        exit_code = run_dstack_cli(["init"], dstack_dir=dstack_dir, repo_dir=tests_public_repo)
        assert exit_code == 0
        exit_code = run_dstack_cli(
            ["secrets", "add", "MY_SECRET", "my_secret_value"],
            dstack_dir=dstack_dir,
            repo_dir=tests_public_repo,
        )
        assert exit_code == 0
        exit_code = run_dstack_cli(
            ["run", "bash", "-c", "echo $MY_SECRET"],
            dstack_dir=dstack_dir,
            repo_dir=tests_public_repo,
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
